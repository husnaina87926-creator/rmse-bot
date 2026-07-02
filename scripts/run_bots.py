"""Unified multi-bot runner: gold + all config crypto symbols (14 accounts as of 2026-07), each $5000, champions + challengers.

  gold (XAUUSD) — TwelveData 15m, momentum LONG (up-regime), USD news filter
  crypto (all crypto_rules.symbols) — Binance 4h, all-weather (short down-regime / long up-regime)

Each instrument also runs a CHALLENGER (live rules + a self-learning candidate) so new
edges are forward-tested before promotion. Live rules come from state/live_rules.json
(promoted by self-improvement), falling back to config. No key needed for crypto.
Run from project root:  python scripts/run_bots.py
"""
import sys
import os
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import fetch_twelvedata, fetch_dukascopy
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.regime import regime_state
from rmse_bot.paper_trader import load_state, save_state, step, default_params
from rmse_bot.news_filter import fetch_calendar, is_news_blocked, nearest_event
from rmse_bot.self_improve import load_live_rules, rules_for, candidate_list, chal_account
from rmse_bot.journal import integrity_check, diff_and_journal, append_event
from rmse_bot.discovery import set_market_context

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")


def crypto_params(cfg):
    cr, ex = cfg["crypto_rules"], cfg["crypto_rules"]["exit"]
    p = default_params(cfg)
    p.update(sl_atr=ex["sl_atr"], rr=ex["rr"], max_hold=ex["max_hold"],
             be_atr=ex.get("be_atr", 0.0), risk_pct=cr["risk_pct"], leverage=cr["leverage"])
    return p


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    now = dt.datetime.now(dt.timezone.utc)
    key = os.environ.get("TWELVE_DATA_KEY")
    start_bal = cfg["account"]["size_usd"]
    rf = cfg.get("regime_filter", {})
    ep, rn = rf.get("ema_period", 100), rf.get("rise_n", 20)
    live = load_live_rules(os.path.join(STATE, "live_rules.json"))
    cand_path = os.path.join(STATE, "candidates.json")
    candidates = json.load(open(cand_path)) if os.path.exists(cand_path) else {}

    accts = [{"name": "gold", "symbol": "XAUUSD", "kind": "gold", "params": default_params(cfg)}]
    for sym in cfg["crypto_rules"]["symbols"]:
        accts.append({"name": sym[:-4].lower(), "symbol": sym, "kind": "crypto", "params": crypto_params(cfg)})

    # cross-market context (BTC daily) + news calendar — both fail-open
    try:
        set_market_context(fetch_binance_klines("BTCUSDT", "1d",
                                                now - dt.timedelta(days=400), now))
    except Exception as e:
        print(f"  WARN btc context: {e}")
    try:
        events = fetch_calendar()
    except Exception as e:
        events = []
        print(f"  WARN calendar: {e}")
    title, hours = nearest_event(now, events)
    extra = {"news_event": title, "news_h": hours}

    print(f"[{now:%Y-%m-%d %H:%M} UTC] bots step")
    for acc in accts:
        sym = acc["symbol"]
        try:
            if acc["kind"] == "gold":
                trade = fetch_twelvedata(sym, "15m", key) if key else \
                    fetch_dukascopy(sym, "15m", now - dt.timedelta(days=12), now)
                daily = fetch_twelvedata(sym, "1d", key, 250) if key else \
                    fetch_dukascopy(sym, "1d", now - dt.timedelta(days=400), now)
            else:
                trade = fetch_binance_klines(sym, "4h", now - dt.timedelta(days=60), now)
                daily = fetch_binance_klines(sym, "1d", now - dt.timedelta(days=300), now)
        except Exception as e:
            print(f"  WARN {acc['name']} fetch failed: {e}")
            continue

        # DATA INTEGRITY GUARD: never act on broken data (dup/backwards/gappy/stale bars)
        interval_s = 900 if acc["kind"] == "gold" else 14400
        ok, reason = integrity_check(trade, interval_s,
                                     allow_session_gaps=(acc["kind"] == "gold"))
        if not ok:
            print(f"  WARN {acc['name']} data integrity: {reason} — skipping this round")
            append_event(STATE, {"type": "data_skip", "account": acc["name"],
                                 "symbol": sym, "reason": reason})
            continue

        reg = regime_state(daily, ep, rn)
        news_blocked = False
        if acc["kind"] == "gold" and cfg.get("news_filter", {}).get("enabled"):
            try:
                nf = cfg["news_filter"]
                news_blocked = is_news_blocked(now, events, nf.get("currencies", ["USD"]),
                                               nf.get("impacts", ["High"]), nf.get("window_min", 30))
            except Exception as e:
                print(f"  WARN news: {e}")

        champ_rules = rules_for(sym, cfg, live)
        data, rs = {sym: trade}, {sym: reg}

        bar_time = trade["time"].iloc[-1]

        # champion
        cs = load_state(os.path.join(STATE, f"{acc['name']}.json"), start_bal)
        b_open, b_n = [dict(p) for p in cs["open"]], len(cs["closed"])
        step(cs, data, cfg, {sym: champ_rules}, now, params=acc["params"],
             regime_state_by_symbol=rs, news_blocked=news_blocked)
        save_state(cs, os.path.join(STATE, f"{acc['name']}.json"))
        diff_and_journal(STATE, acc["name"], b_open, b_n, cs, bar_time, interval_s, extra=extra)

        # challengers (champion + one tournament candidate each), if any
        chal_line = ""
        for cand in candidate_list(candidates, sym):
            cn = chal_account(acc["name"], cand.get("slot", 0))
            chs = load_state(os.path.join(STATE, f"{cn}.json"), start_bal)
            b_open, b_n = [dict(p) for p in chs["open"]], len(chs["closed"])
            step(chs, data, cfg, {sym: champ_rules + [cand["rule"]]}, now, params=acc["params"],
                 regime_state_by_symbol=rs, news_blocked=news_blocked)
            save_state(chs, os.path.join(STATE, f"{cn}.json"))
            diff_and_journal(STATE, cn, b_open, b_n, chs, bar_time, interval_s, extra=extra)
            chal_line += f" | {cn.split('_', 1)[1]} ${chs['balance']:.0f}/{len(chs['closed'])}tr"

        wins = [t for t in cs["closed"] if t["pnl"] > 0]
        wr = len(wins) / len(cs["closed"]) if cs["closed"] else 0
        print(f"  {acc['name']:5} {sym:8} regime={reg or '-':4} balance=${cs['balance']:.2f} "
              f"open={len(cs['open'])} closed={len(cs['closed'])} win={wr:.0%}{chal_line}")


if __name__ == "__main__":
    main()
