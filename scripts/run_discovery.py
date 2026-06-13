"""Run the Move Discovery engine on cached real data.

For each instrument: label every bar's forward move, record the conditions present,
and report which conditions carry an edge -- with an out-of-sample (OOS) check so we
don't fool ourselves. 'holds=True' = the edge survived on unseen data.

Run from project root:  python scripts/run_discovery.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from rmse_bot.data_feed import load_csv
from rmse_bot.discovery import run_discovery

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 20)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SYMBOLS = ["XAUUSD", "EURUSD"]


def main():
    for sym in SYMBOLS:
        path = os.path.join(DATA_DIR, f"{sym}_15m.csv")
        df = load_csv(path)
        res = run_discovery(df, split=0.7, horizon=12, k_atr=1.5, min_count=200)
        print(f"\n{'='*70}\n{sym}  ({len(df)} bars, 15m)\n{'='*70}")
        print("Baseline (random bar):  P(up move) and P(down move) are about equal.")
        print(res.to_string(index=False))
        held = res[res["holds"]]
        print(f"\n>>> Conditions whose edge HELD out-of-sample: {len(held)}")
        if not held.empty:
            print(held[["condition", "count", "net", "oos_net"]].to_string(index=False))


if __name__ == "__main__":
    main()
