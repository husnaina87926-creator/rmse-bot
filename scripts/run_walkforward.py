"""Walk-forward validation of the edge strategies on real data.

Tiles the 2.4yr timeline into many train->test windows. For each window the SL/RR/
hold config is tuned on train and applied to the *next* unseen test slice. If most
windows stay profitable across different periods, the edge is regime-robust.

Run from project root:  python scripts/run_walkforward.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import math
from rmse_bot.config import load_config
from rmse_bot.data_feed import load_csv
from rmse_bot.backtest import walk_forward

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

RULES = {
    "XAUUSD": [{"direction": "buy", "when": ["trend_up", "rsi_overbought", "high_vol"]}],
    "EURUSD": [{"direction": "buy", "when": ["rsi_oversold", "high_vol"]}],
}
GRID = [(1.5, 1.0, 12), (1.5, 1.0, 24), (2.0, 1.0, 24), (2.0, 0.8, 24), (2.0, 1.5, 24)]
TRAIN_LEN = 12000   # ~5 months of 15m bars
TEST_LEN = 4000     # ~7 weeks


def main():
    cfg = load_config("config.yaml")
    for sym, rules in RULES.items():
        df = load_csv(os.path.join(DATA_DIR, f"{sym}_15m.csv"))
        folds = walk_forward(df, cfg, cfg["instruments"][sym], rules,
                             TRAIN_LEN, TEST_LEN, GRID, min_train_trades=20)
        print(f"\n{'='*78}\n{sym}  ({len(folds)} walk-forward windows)\n{'='*78}")
        print(f"{'test_start':<12}{'cfg(SL/RR/hold)':<18}{'trades':>7}{'win':>6}{'PF':>7}{'return$':>10}")
        prof = 0
        total = 0.0
        finite_pf = []
        for f in folds:
            cfgs = f"{f['sl']}/{f['rr']}/{f['hold']}"
            pf = f["test_pf"]
            print(f"{f['start_time']:<12}{cfgs:<18}{f['test_trades']:>7}{f['test_win']:>6.0%}"
                  f"{pf:>7}{f['test_return']:>10.2f}")
            if f["test_return"] > 0:
                prof += 1
            total += f["test_return"]
            if not math.isinf(pf):
                finite_pf.append(pf)
        avg_pf = sum(finite_pf) / len(finite_pf) if finite_pf else float("nan")
        print(f"\n  Profitable windows: {prof}/{len(folds)}  |  avg test PF: {avg_pf:.2f}  "
              f"|  summed test return: ${total:.2f} (on $100, periodically re-tuned)")


if __name__ == "__main__":
    main()
