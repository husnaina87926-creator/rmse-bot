"""Fetch real data via yfinance and run the backtest. Prints a metrics report.

Note: yfinance 15m history is limited (~60 days). For a full 2-3yr backtest we
plug a downloaded CSV in a later step; this proves the pipeline end-to-end.

Run from project root:  python scripts/run_backtest.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import fetch_yfinance
from rmse_bot.backtest import backtest


def main():
    cfg = load_config("config.yaml")
    for name, instr in cfg["instruments"].items():
        sym = instr["yf_symbol"]
        try:
            df15 = fetch_yfinance(sym, interval="15m", period="60d")
            df1h = fetch_yfinance(sym, interval="1h", period="730d")
        except Exception as e:
            print(f"\n=== {name} ({sym}) === data fetch failed: {e}")
            continue
        res = backtest(df15, df1h, cfg, instr)
        print(f"\n=== {name} ({sym}) ===  bars15m={len(df15)} bars1h={len(df1h)}")
        for k, v in res.metrics.items():
            if isinstance(v, float):
                print(f"  {k}: {v:.4f}")
            else:
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
