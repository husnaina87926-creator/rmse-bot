"""Quick diagnostic: show whether each strategy condition is met on the latest candle.
Explains WHY there is or isn't a signal right now. Run: python scripts/diagnose.py"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import fetch_dukascopy
from rmse_bot.discovery import build_features


def main():
    cfg = load_config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"))
    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(days=12)
    for sym, rules in cfg["edge_rules"].items():
        df = fetch_dukascopy(sym, "15m", start, now)
        f = build_features(df).iloc[-1]
        need = rules[0]["when"]
        last_t = str(df["time"].iloc[-1])[:16]
        print(f"\n=== {sym} (latest candle {last_t}, price {df['close'].iloc[-1]:.4f}) ===")
        print(f"  Trade needs: {need}")
        all_ok = True
        for c in need:
            ok = bool(f[c])
            all_ok = all_ok and ok
            mark = "OK " if ok else "NO "
            print(f"    [{mark}] {c} = {ok}")
        print(f"  >> Signal: {'YES - TRADE!' if all_ok else 'no (not all conditions met)'}")


if __name__ == "__main__":
    main()
