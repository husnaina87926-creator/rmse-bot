"""Step the champion AND challenger virtual accounts on the same live data.

Champion = current strategy (state/paper_state.json — the live account).
Challengers = champion + one self-learning candidate each (state/challenger_N.json).
All run on identical live candles so their forward results are directly comparable.

Run from project root:  python scripts/run_accounts.py
"""
import sys
import os
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import fetch_dukascopy, fetch_twelvedata
from rmse_bot.paper_trader import load_state, save_state, step
from rmse_bot.champion_challenger import build_accounts, compare_accounts
from rmse_bot.news_filter import fetch_calendar, is_news_blocked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "state", "candidate_registry.json")
HISTORY_DAYS = 12


def _fetch(symbols, now):
    td = os.environ.get("TWELVE_DATA_KEY")
    start = now - dt.timedelta(days=HISTORY_DAYS)
    data = {}
    for sym in symbols:
        try:
            data[sym] = fetch_twelvedata(sym, "15m", td) if td else fetch_dukascopy(sym, "15m", start, now)
        except Exception as e:
            print(f"WARN {sym} fetch failed: {e}")
    return data, ("TwelveData" if td else "Dukascopy")


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    registry = None
    if os.path.exists(REGISTRY):
        with open(REGISTRY) as f:
            registry = json.load(f)

    accounts = build_accounts(cfg, registry)
    symbols = sorted({s for a in accounts for s in a["rules"]})
    now = dt.datetime.now(dt.timezone.utc)
    data, source = _fetch(symbols, now)

    # high-impact news filter (fail-open: if it can't fetch, don't block trading)
    nf = cfg.get("news_filter", {})
    news_blocked = False
    if nf.get("enabled"):
        try:
            events = fetch_calendar()
            news_blocked = is_news_blocked(now, events,
                                           currencies=nf.get("currencies", ["USD"]),
                                           impacts=nf.get("impacts", ["High"]),
                                           window_min=nf.get("window_min", 30))
        except Exception as e:
            print(f"WARN news fetch failed: {e}")

    named_states = []
    for acc in accounts:
        path = os.path.join(ROOT, acc["state"])
        state = load_state(path, cfg["account"]["size_usd"])
        step(state, data, cfg, acc["rules"], now, news_blocked=news_blocked)
        save_state(state, path)
        named_states.append((acc["name"], state))

    print(f"[{now:%Y-%m-%d %H:%M} UTC] accounts step done (data: {source}, "
          f"{len(accounts)} accounts, news_blocked={news_blocked})")
    for r in compare_accounts(named_states):
        print(f"  {r['name']:<14} balance=${r['balance']:.2f}  trades={r['trades']}  "
              f"open={r['open']}  win={r['win']:.0%}  pnl=${r['pnl']:.2f}")


if __name__ == "__main__":
    main()
