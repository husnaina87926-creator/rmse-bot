"""Strategy lab: the bot composes & ranks its own strategies, writes a leaderboard.

Ranked by ROBUST profit (return x cross-window consistency), NOT win rate. The top
strategy is a CANDIDATE — forward-test it as a challenger before promoting.

Run from project root:  python scripts/run_strategy_lab.py
"""
import sys
import os
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import load_csv, fetch_dukascopy
from rmse_bot.strategy_generator import generate_strategies

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(ROOT, "reports")
STATE_DIR = os.path.join(ROOT, "state")


def _get_data(sym, now):
    path = os.path.join(ROOT, "data", f"{sym}_15m.csv")
    if os.path.exists(path):
        return load_csv(path)
    return fetch_dukascopy(sym, "15m", now - dt.timedelta(days=400), now)


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    now = dt.datetime.now(dt.timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    md = [f"# RMSE_BOT Strategy Lab — {date_str}\n",
          "_Bot-generated strategies ranked by ROBUST profit (return x window-consistency), "
          "NOT win rate. Top = CANDIDATE; forward-test before promoting._\n"]
    board = {}

    for sym in cfg["edge_rules"]:
        df = _get_data(sym, now)
        ranked = generate_strategies(df, cfg, sym)
        board[sym] = ranked[:15]
        md.append(f"\n## {sym}  ({len(df)} bars, {len(ranked)} strategies tested)\n")
        md.append(f"{'#':>2}  {'score':>7} {'return$':>8} {'PF':>5} {'win':>5} {'maxDD$':>7} {'consist':>7}  rule (dir, entry, exit)\n")
        for i, s in enumerate(ranked[:12], 1):
            md.append(f"{i:>2}  {s['score']:>7.2f} {s['return']:>8.2f} {s['pf']:>5.2f} "
                      f"{s['win']:>5.0%} {s['maxdd']:>7.2f} {s['consistency']:>7.0%}  "
                      f"{s['direction']} [{' & '.join(s['entry'])}] rr{s['exit']['rr']}/be{s['exit']['be']}\n")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, f"strategies_{date_str}.md"), "w") as f:
        f.write("".join(md))
    with open(os.path.join(STATE_DIR, "strategy_leaderboard.json"), "w") as f:
        json.dump({"date": date_str, "board": board}, f, indent=2)
    print("".join(md))


if __name__ == "__main__":
    main()
