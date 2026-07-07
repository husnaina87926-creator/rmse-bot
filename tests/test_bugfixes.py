"""Tests for the 2026-07-05 senior bug-hunt fixes."""
import datetime as dt
import json
import os

import pandas as pd

from rmse_bot.atomic import atomic_json_dump
from rmse_bot.data_feed import drop_forming
from rmse_bot.risk import position_size, trade_cost
from rmse_bot.paper_trader import scan_for_entries, new_state
from rmse_bot.self_improve import should_promote, should_demote, keep_candidate


def test_atomic_json_dump_roundtrip(tmp_path):
    p = os.path.join(str(tmp_path), "x", "y.json")
    atomic_json_dump({"a": 1}, p)
    assert json.load(open(p)) == {"a": 1}
    atomic_json_dump({"a": 2}, p)                      # overwrite via rename
    assert json.load(open(p)) == {"a": 2}
    assert not [f for f in os.listdir(os.path.dirname(p)) if f.startswith(".tmp-")]


def test_drop_forming_keeps_closed_bars_only():
    now = dt.datetime(2026, 7, 5, 20, 0, 5, tzinfo=dt.timezone.utc)   # 5s after a 4h close
    times = pd.date_range("2026-07-04 20:00", periods=7, freq="4h", tz="UTC")  # last=20:00 forming
    df = pd.DataFrame({"time": times, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0})
    out = drop_forming(df, 14400, now)
    assert len(out) == 6                                # forming 20:00 bar dropped
    assert str(out["time"].iloc[-1]) == "2026-07-05 16:00:00+00:00"
    # naive timestamps handled; nothing dropped when all bars are old
    old = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=5, freq="4h"),
                        "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0})
    assert len(drop_forming(old, 14400, now)) == 5


def test_position_size_includes_costs():
    # without costs: 10% of 5000 = $500 risk over $4 stop distance -> 125 units
    assert position_size(5000, 10, 100, 96, 1.0) == 125.0
    # with $0.20/lot round-trip cost the size shrinks so loss+cost == $500 exactly
    lots = position_size(5000, 10, 100, 96, 1.0, cost_per_lot=0.2)
    assert abs(lots * 4 + lots * 0.2 - 500.0) < 1e-9
    assert lots < 125.0


def _mkdf(n=300, price=100.0):
    t = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({"time": t, "open": price, "high": price + 60,
                         "low": price - 60, "close": price})


def test_reentry_cooldown_matches_backtest(monkeypatch):
    """After a close, no new entry on that symbol until max_hold bars from the
    previous ENTRY have passed (backtest does i += max_hold)."""
    import rmse_bot.paper_trader as pt
    feats = pd.DataFrame({"always": [True] * 300})
    monkeypatch.setattr("rmse_bot.discovery.build_features", lambda df: feats)
    cfg = {"instruments": {"X": {"contract_size": 1.0}}, "risk": {}, "account": {},
           "strategy": {}, "exits": {}}
    params = {"sl_atr": 2.0, "rr": 1.0, "max_hold": 24, "be_atr": 0, "trail_atr": 0,
              "risk_pct": 1.0, "leverage": 20, "atr_period": 14, "max_open_trades": 9,
              "max_trades_per_day": 99, "max_daily_loss_pct": 100, "size_usd": 5000}
    df = _mkdf()
    rules = {"X": [{"direction": "buy", "when": ["always"]}]}
    st = new_state(5000)
    # a trade that ENTERED 10 bars ago (within the 24-bar hold window) just closed
    st["closed"].append({"symbol": "X", "pnl": -50.0,
                         "open_time": str(df["time"].iloc[-10]),
                         "close_time": str(df["time"].iloc[-2])})
    scan_for_entries(st, {"X": df}, cfg, rules, params=params)
    assert st["open"] == []                             # cooldown blocks re-entry
    st["closed"][0]["open_time"] = str(df["time"].iloc[-1] - pd.Timedelta(hours=4 * 30))
    scan_for_entries(st, {"X": df}, cfg, rules, params=params)
    assert len(st["open"]) == 1                         # window passed -> trade allowed


def _closed(pnls, rule=None):
    return [{"pnl": p, "rule": rule} if rule else {"pnl": p} for p in pnls]


def test_promotion_uses_candidate_attributed_trades_only():
    cand = {"direction": "sell", "when": ["x"], "regime": "down"}
    champ_r = {"direction": "sell", "when": ["base"], "regime": "down"}
    champ = {"balance": 5100, "closed": _closed([2.5] * 40, champ_r)}
    # challenger account rich from CHAMPION rules; candidate itself has 10 flat trades
    chall = {"balance": 5400,
             "closed": _closed([9.0] * 40, champ_r) + _closed([1.0] * 10, cand)}
    assert should_promote(champ, chall, 5000, 30, cand_rule=cand) is False   # only 10 own
    chall2 = {"balance": 5400,
              "closed": _closed([1.0] * 40, champ_r) + _closed([8.0] * 35, cand)}
    assert should_promote(champ, chall2, 5000, 30, cand_rule=cand) is True
    # legacy fallback: untagged account still judged on all trades
    legacy = {"balance": 5300, "closed": _closed([7.5] * 40)}
    assert should_promote(champ, legacy, 5000, 30, cand_rule=cand) is True


def test_demote_is_rule_attributed():
    promoted_at = "2026-06-01T00:00:00+00:00"
    promo = {"direction": "buy", "when": ["p"], "regime": "up"}
    base = {"direction": "sell", "when": ["b"], "regime": "down"}
    since = ([{"pnl": -30.0, "close_time": "2026-06-10 00:00:00", "rule": base}] * 25
             + [{"pnl": 5.0, "close_time": "2026-06-10 00:00:00", "rule": promo}] * 25)
    champ = {"closed": since}
    # base rules lost money, the promoted rule itself is profitable -> NOT demoted
    assert should_demote(champ, promoted_at, rule=promo) is False
    assert should_demote(champ, promoted_at) is True    # aggregate (legacy) would demote


def test_keep_candidate_counts_own_trial_only():
    cand_rule = {"direction": "sell", "when": ["x"], "regime": "down"}
    champ_r = {"direction": "sell", "when": ["base"], "regime": "down"}
    existing = {"rule": cand_rule,
                "born": dt.datetime.now(dt.timezone.utc).isoformat()}
    # 35 champion trades but only 3 candidate trades -> trial NOT over -> keep
    chall = {"closed": _closed([1] * 35, champ_r) + _closed([1] * 3, cand_rule)}
    assert keep_candidate(existing, chall) is True
    chall2 = {"closed": _closed([1] * 5, champ_r) + _closed([1] * 30, cand_rule)}
    assert keep_candidate(existing, chall2) is False    # own 30-trade trial complete


def test_taxonomy_joins_open_tags(tmp_path):
    from rmse_bot.journal import append_event, mistake_taxonomy
    sd = str(tmp_path)
    ot = "2026-07-01 08:00:00"
    append_event(sd, {"type": "open", "account": "btc", "symbol": "BTCUSDT",
                      "open_time": ot, "news_h": 1.0, "llm_sentiment": -2})
    append_event(sd, {"type": "close", "account": "btc", "symbol": "BTCUSDT",
                      "direction": "sell", "outcome": "sl", "pnl": -40.0,
                      "open_time": ot, "close_time": "2026-07-01 20:00:00",
                      "news_h": None, "llm_sentiment": 1})   # close-time tags differ
    mo = mistake_taxonomy(sd)["months"]["2026-07"]
    assert mo["news_window_trades"] == 1                # judged at OPEN, not close
    assert mo["neg_sentiment_trades"] == 1
