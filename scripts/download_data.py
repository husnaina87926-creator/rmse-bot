"""Download real historical 15m data (XAUUSD, EURUSD) from Dukascopy (free, no key)
and cache to data/<symbol>_15m.csv. 1h timeframe is derived by resampling.

Run from project root:  python scripts/download_data.py
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.data_feed import fetch_dukascopy

START = dt.datetime(2024, 1, 1)
END = dt.datetime(2026, 6, 1)
SYMBOLS = ["XAUUSD", "EURUSD"]
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    for sym in SYMBOLS:
        print(f"Downloading {sym} 15m {START.date()}..{END.date()} ...", flush=True)
        df = fetch_dukascopy(sym, "15m", START, END)
        path = os.path.join(DATA_DIR, f"{sym}_15m.csv")
        df.to_csv(path, index=False)
        print(f"  saved {len(df)} bars -> {path}", flush=True)


if __name__ == "__main__":
    main()
