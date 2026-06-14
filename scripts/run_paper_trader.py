"""One paper-trading step on LIVE data. Run every 15 min (cron / GitHub Actions / loop).

Fetches recent candles, updates open virtual trades, opens new ones on signals, and
persists the virtual account to data/paper_state.json. Prints a short status.

Run from project root:  python scripts/run_paper_trader.py
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import fetch_dukascopy, fetch_twelvedata
from rmse_bot.paper_trader import load_state, save_state, step

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "state", "paper_state.json")
HISTORY_DAYS = 12


def _summary(state):
    closed = state["closed"]
    wins = [t for t in closed if t["pnl"] > 0]
    wr = len(wins) / len(closed) if closed else 0.0
    pnl = sum(t["pnl"] for t in closed)
    print(f"balance=${state['balance']:.2f}  open={len(state['open'])}  "
          f"closed={len(closed)}  win={wr:.0%}  realized_pnl=${pnl:.2f}")
    for t in closed[-3:]:
        print(f"  closed {t['symbol']} {t['direction']} {t['outcome']} "
              f"pnl=${t['pnl']:.2f} @ {t['close_time'][:16]}")
    for p in state["open"]:
        print(f"  OPEN {p['symbol']} {p['direction']} entry={p['entry']:.5f} "
              f"sl={p['sl']:.5f} tp={p['tp']:.5f} since {p['open_time'][:16]}")


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    rules = cfg["edge_rules"]
    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(days=HISTORY_DAYS)

    td_key = os.environ.get("TWELVE_DATA_KEY")
    source = "TwelveData" if td_key else "Dukascopy"
    data = {}
    for sym in rules:
        try:
            if td_key:
                data[sym] = fetch_twelvedata(sym, "15m", td_key)
            else:
                data[sym] = fetch_dukascopy(sym, "15m", start, now)
        except Exception as e:
            print(f"WARN {sym} fetch failed ({source}): {e}")

    state = load_state(STATE_PATH, cfg["account"]["size_usd"])
    step(state, data, cfg, rules, now)
    save_state(state, STATE_PATH)
    print(f"[{now:%Y-%m-%d %H:%M} UTC] paper step done (data: {source})")
    _summary(state)


if __name__ == "__main__":
    main()
