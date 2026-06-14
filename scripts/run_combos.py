"""Run combination mining on cached real data.

Tests 2-3 condition combos, keeps only those whose edge holds out-of-sample (OOS).
'bias UP' = price tends to move up when all the conditions are true; 'DOWN' = down.

Run from project root:  python scripts/run_combos.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from rmse_bot.data_feed import load_csv
from rmse_bot.discovery import run_combo_discovery

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 60)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SYMBOLS = ["XAUUSD", "EURUSD"]


def main():
    for sym in SYMBOLS:
        df = load_csv(os.path.join(DATA_DIR, f"{sym}_15m.csv"))
        res = run_combo_discovery(df, split=0.7, sizes=(2, 3),
                                  min_count=300, oos_min_count=100, edge_min=0.05)
        held = res[res["holds"]].copy()
        print(f"\n{'='*80}\n{sym}  ({len(df)} bars)  |  combos tested: {len(res)}  |  held OOS: {len(held)}\n{'='*80}")
        if held.empty:
            print("No 2-3 condition combo kept a >=5% edge out-of-sample.")
        else:
            show = held[["conditions", "size", "count_is", "count_oos",
                         "net_is", "net_oos", "bias"]].head(20)
            print(show.to_string(index=False))


if __name__ == "__main__":
    main()
