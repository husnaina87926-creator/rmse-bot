"""Generate today's daily report + append to the running history summary.

Writes:
  reports/<YYYY-MM-DD>.md   (that day's digest; overwritten if re-run same day)
  reports/SUMMARY.csv        (one row per day, history)

Idempotent: re-running on the same day replaces that day's outputs, no duplicates.
Run from project root:  python scripts/run_daily_report.py
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.paper_trader import load_state
from rmse_bot.reporting import compute_stats, daily_slice, render_daily_md, render_summary_row

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(ROOT, "reports")
SUMMARY = os.path.join(REPORTS_DIR, "SUMMARY.csv")
HEADER = "date,trades_today,pnl_today,balance,total_trades,win_rate\n"


def _update_summary(date_str: str, row: str) -> None:
    lines = [HEADER]
    if os.path.exists(SUMMARY):
        with open(SUMMARY) as f:
            lines = [ln for ln in f.readlines() if ln.strip() and ln != HEADER]
        lines = [HEADER] + [ln for ln in lines if not ln.startswith(date_str + ",")]
    lines.append(row)
    with open(SUMMARY, "w") as f:
        f.writelines(lines)


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    per = cfg["account"]["size_usd"]
    date_str = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    # aggregate ALL accounts: gold + every crypto symbol from config (14 as of 2026-07)
    names = ["gold"] + [sym[:-4].lower() for sym in cfg["crypto_rules"]["symbols"]]
    closed, open_count = [], 0
    for name in names:
        s = load_state(os.path.join(ROOT, "state", f"{name}.json"), per)
        closed += s.get("closed", [])
        open_count += len(s.get("open", []))
    closed.sort(key=lambda t: str(t.get("close_time", "")))
    start_bal = per * len(names)

    day = compute_stats(daily_slice(closed, date_str), start_bal)
    cum = compute_stats(closed, start_bal)
    cum["balance"] = round(start_bal + cum["total_pnl"], 2)   # combined across accounts

    os.makedirs(REPORTS_DIR, exist_ok=True)
    md = render_daily_md(date_str, day, cum, open_count=open_count)
    with open(os.path.join(REPORTS_DIR, f"{date_str}.md"), "w") as f:
        f.write(md)
    _update_summary(date_str, render_summary_row(date_str, day, cum))

    print(md)


if __name__ == "__main__":
    main()
