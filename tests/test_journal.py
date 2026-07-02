import datetime as dt
import json
import os

import pandas as pd

from rmse_bot.journal import (
    append_event, read_events, diff_and_journal, integrity_check,
    health_snapshot, run_postmortems, run_counterfactuals, counterfactual_summary,
)


def _df(times, o=100.0, h=101.0, l=99.0, c=100.5):
    return pd.DataFrame({"time": pd.to_datetime(times),
                         "open": o, "high": h, "low": l, "close": c})


def _times(n, interval_s, end=None):
    end = end or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return [end - dt.timedelta(seconds=interval_s * (n - 1 - i)) for i in range(n)]


def test_integrity_ok_and_failures():
    iv = 14400
    ok, r = integrity_check(_df(_times(60, iv)), iv)
    assert ok and r == "ok"

    # too few bars
    ok, r = integrity_check(_df(_times(10, iv)), iv)
    assert not ok and r == "too_few_bars"

    # duplicate timestamps
    t = _times(60, iv); t[5] = t[4]
    ok, r = integrity_check(_df(t), iv)
    assert not ok and r == "duplicate_timestamps"

    # internal gap (missing candle)
    t = _times(60, iv)
    del t[30]                                                      # one candle missing -> 2*iv gap
    ok, r = integrity_check(_df(t), iv)
    assert not ok and r == "gap_missing_candles"

    # stale last candle (dead feed)
    old = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(days=5)
    ok, r = integrity_check(_df(_times(60, iv, end=old)), iv)
    assert not ok and r == "stale_last_candle"

    # session market (gold): weekend gap allowed, only multi-day staleness rejected
    t = _times(60, 900)
    t = t[:30] + [x + dt.timedelta(days=2) for x in t[30:]]        # weekend-style gap
    ok, r = integrity_check(_df(t), 900, allow_session_gaps=True,
                            now=dt.datetime.fromtimestamp(
                                t[-1].timestamp(), dt.timezone.utc))
    assert ok


def test_diff_and_journal_records_opens_and_closes(tmp_path):
    sd = str(tmp_path)
    pos = {"symbol": "BTCUSDT", "direction": "sell", "entry": 100.0, "sl": 104.0,
           "tp": 96.0, "lots": 1.0, "atr": 2.0, "open_time": "2026-07-01 04:00:00+00:00",
           "rule": {"direction": "sell", "when": ["rsi_bear"]}, "regime_at_open": "down"}
    closed = {"symbol": "BTCUSDT", "direction": "sell", "entry": 100.0, "exit": 96.0,
              "outcome": "tp", "pnl": 4.0, "open_time": "2026-07-01 04:00:00+00:00",
              "close_time": "2026-07-01 16:00:00+00:00", "lots": 1.0}
    # one pre-existing open closes; one new open appears
    before_open = [pos]
    state = {"open": [dict(pos, open_time="2026-07-02 04:00:00+00:00")],
             "closed": [closed], "balance": 5004.0}
    diff_and_journal(sd, "btc", before_open, 0, state,
                     bar_time="2026-07-02 04:00:00+00:00", interval_s=14400)
    evs = read_events(sd)
    kinds = [e["type"] for e in evs]
    assert kinds.count("open") == 1 and kinds.count("close") == 1
    close_ev = next(e for e in evs if e["type"] == "close")
    assert close_ev["sl"] == 104.0 and close_ev["tp"] == 96.0      # enriched from position
    assert close_ev["rule"]["when"] == ["rsi_bear"]
    open_ev = next(e for e in evs if e["type"] == "open")
    assert open_ev["account"] == "btc" and open_ev["regime_at_open"] == "down"


def test_health_snapshot_flags_unhealthy(tmp_path):
    sd = str(tmp_path)
    good = {"balance": 5500, "open": [],
            "closed": [{"pnl": 10}] * 25, "history": []}
    bad = {"balance": 4800, "open": [],
           "closed": [{"pnl": 50}] * 10 + [{"pnl": -12}] * 20, "history": []}
    json.dump(good, open(os.path.join(sd, "good.json"), "w"))
    json.dump(bad, open(os.path.join(sd, "bad.json"), "w"))
    h = health_snapshot(sd, ["good", "bad"], 5000)
    assert h["good"]["unhealthy"] is False
    assert h["bad"]["unhealthy"] is True
    assert os.path.exists(os.path.join(sd, "health.json"))


def test_postmortem_tp_hit_after_exit(tmp_path):
    sd = str(tmp_path)
    # a sell closed by TIME exit at 100; afterwards price fell to 90 (tp was 95 -> hit after exit)
    append_event(sd, {"type": "close", "account": "btc", "symbol": "BTCUSDT",
                      "direction": "sell", "exit": 100.0, "tp": 95.0, "atr": 2.0,
                      "outcome": "time", "pnl": 0.0,
                      "close_time": "2026-07-01 00:00:00"})
    fut_times = pd.date_range("2026-07-01 04:00:00", periods=10, freq="4h")
    df = pd.DataFrame({"time": fut_times, "open": 99.0, "high": 99.5,
                       "low": 90.0, "close": 92.0})
    n = run_postmortems(sd, lambda sym: df)
    assert n == 1
    pm = [e for e in read_events(sd) if e["type"] == "postmortem"][0]
    assert pm["tp_hit_after_exit"] is True
    assert pm["left_on_table_atr"] == 5.0          # (100-90)/2 ATR left on the table
    # second run: no duplicates
    assert run_postmortems(sd, lambda sym: df) == 0


def test_counterfactuals_and_summary(tmp_path):
    sd = str(tmp_path)
    # a sell that TIME-exited flat at 100; afterwards price kept falling to 92
    append_event(sd, {"type": "close", "account": "btc", "symbol": "BTCUSDT",
                      "direction": "sell", "entry": 100.0, "exit": 100.0,
                      "sl": 104.0, "tp": 96.0, "atr": 2.0, "outcome": "time", "pnl": 0.0,
                      "open_time": "2026-07-01 00:00:00",
                      "close_time": "2026-07-05 00:00:00"})
    fut = pd.date_range("2026-07-01 04:00:00", periods=48, freq="4h")
    px = [100 - 0.4 * i for i in range(48)]                     # steady decline
    df = pd.DataFrame({"time": fut, "open": px, "high": [p + 0.1 for p in px],
                       "low": [p - 0.1 for p in px], "close": px})
    n = run_counterfactuals(sd, lambda sym: df)
    assert n == 1
    ev = [e for e in read_events(sd) if e["type"] == "counterfactual"][0]
    assert ev["base_R"] == 0.0                                  # actual trade made nothing
    assert ev["variants"]["rr_2.0"]["outcome"] == "tp"          # decline reached 2R target
    assert ev["variants"]["rr_2.0"]["R"] == 2.0
    assert ev["variants"]["hold_48"]["R"] == 1.0                # 1R tp hit on longer hold
    s = counterfactual_summary(sd)
    assert s["n_trades"] == 1
    assert s["variants"]["rr_2.0"]["avg_R"] > s["base_avg_R"]   # lesson: exited too early
    assert run_counterfactuals(sd, lambda sym: df) == 0         # no duplicates


def test_regime_ledger_and_warnings(tmp_path):
    from rmse_bot.journal import regime_ledger, ledger_warnings
    sd = str(tmp_path)
    r_dn = {"direction": "sell", "when": ["rsi_bear"], "regime": "down"}
    closed = ([{"pnl": 10.0, "rule": r_dn, "regime_at_open": "down"}] * 12
              + [{"pnl": -5.0, "rule": r_dn, "regime_at_open": "none"}] * 11
              + [{"pnl": 3.0}])                                # pre-tagging era trade
    json.dump({"balance": 5100, "open": [], "closed": closed, "history": []},
              open(os.path.join(sd, "btc.json"), "w"))
    led = regime_ledger(sd, ["btc", "missing"])
    rk = "sell rsi_bear [down]"
    assert led["btc"][rk]["down"] == {"n": 12, "net": 120.0, "win": 1.0}
    assert led["btc"][rk]["none"]["net"] == -55.0
    assert led["btc"]["untagged"]["none"]["n"] == 1
    assert os.path.exists(os.path.join(sd, "regime_ledger.json"))
    warns = ledger_warnings(led)                               # loses in regime=none, n>=10
    assert len(warns) == 1 and "regime=none" in warns[0] and "-55.0" in warns[0]


def _watch_df(direction, n_days=200, spike_last=False):
    """4h OHLC: rising or falling ramp; optional volatility spike on the last bars."""
    rows = []
    for d in range(n_days):
        px = 100 + 2 * d if direction == "up" else 500 - 2 * d
        for h in (0, 4, 8, 12, 16, 20):
            wide = 30 if (spike_last and d >= n_days - 3) else 1
            rows.append({"time": pd.Timestamp("2024-01-01", tz="UTC")
                         + pd.Timedelta(days=d, hours=h),
                         "open": px, "high": px + wide, "low": px - wide, "close": px})
    return pd.DataFrame(rows)


def test_regime_watch_flip_and_vol_break(tmp_path):
    from rmse_bot.journal import regime_watch_pass
    sd = str(tmp_path)
    json.dump({"balance": 5000, "closed": [], "history": [],
               "open": [{"symbol": "BTCUSDT", "regime_at_open": "up"}]},
              open(os.path.join(sd, "btc.json"), "w"))
    up = _watch_df("up")
    # first pass: baseline recorded, no flip event
    log = regime_watch_pass(sd, lambda s: up, ["BTCUSDT"], {"BTCUSDT": "btc"},
                            ema_period=10, rise_n=3)
    assert not [e for e in read_events(sd) if e["type"] == "regime_flip"]
    # regime turns down -> flip journaled, open position from old regime flagged
    dn = _watch_df("down")
    log = regime_watch_pass(sd, lambda s: dn, ["BTCUSDT"], {"BTCUSDT": "btc"},
                            ema_period=10, rise_n=3)
    ev = [e for e in read_events(sd) if e["type"] == "regime_flip"][0]
    assert ev["from"] == "up" and ev["to"] == "down"
    assert ev["open_positions_from_old_regime"] == 1
    assert any("REGIME FLIP" in ln and "CAUTION" in ln for ln in log)

def test_vol_break_fires_once(tmp_path):
    from rmse_bot.journal import regime_watch_pass
    sd = str(tmp_path)
    up = _watch_df("up")                       # rising ramp: ATR%% of price DEclines
    log = regime_watch_pass(sd, lambda s: up, ["BTCUSDT"], {"BTCUSDT": "btc"},
                            ema_period=10, rise_n=3)
    assert not [e for e in read_events(sd) if e["type"] == "vol_break"]
    # volatility spike -> vol_break journaled once, not repeated while flag holds
    spiky = _watch_df("up", spike_last=True)
    log = regime_watch_pass(sd, lambda s: spiky, ["BTCUSDT"], {"BTCUSDT": "btc"},
                            ema_period=10, rise_n=3)
    assert any("VOL BREAK" in ln for ln in log)
    regime_watch_pass(sd, lambda s: spiky, ["BTCUSDT"], {"BTCUSDT": "btc"},
                      ema_period=10, rise_n=3)
    assert len([e for e in read_events(sd) if e["type"] == "vol_break"]) == 1
