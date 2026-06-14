"""Backtest the discovery-derived edge strategies with real costs.

Rules came from run_combos.py (OOS-validated):
  XAUUSD: buy when trend_up & rsi_overbought & high_vol   (momentum continuation)
  EURUSD: buy when rsi_oversold & high_vol                (mean-reversion bounce)

Reports metrics on the FULL period and on the unseen last-30% slice.
Run from project root:  python scripts/run_edge_backtest.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import load_csv
from rmse_bot.backtest import backtest_edge

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

RULES = {
    "XAUUSD": [{"direction": "buy", "when": ["trend_up", "rsi_overbought", "high_vol"]}],
    "EURUSD": [{"direction": "buy", "when": ["rsi_oversold", "high_vol"]}],
}


def _report(tag, res):
    m = res.metrics
    print(f"  [{tag}] trades={m['num_trades']}  win={m['win_rate']:.0%}  "
          f"PF={m['profit_factor']:.2f}  maxDD=${m['max_drawdown']:.2f}  "
          f"return=${m['total_return']:.2f}")


def main():
    cfg = load_config("config.yaml")
    for sym, rules in RULES.items():
        df = load_csv(os.path.join(DATA_DIR, f"{sym}_15m.csv"))
        cut = int(len(df) * 0.7)
        oos = df.iloc[cut:].reset_index(drop=True)
        print(f"\n=== {sym} === rule: {rules[0]['direction']} when {rules[0]['when']}")
        _report("FULL 2.4yr", backtest_edge(df, cfg, cfg["instruments"][sym], rules))
        _report("UNSEEN 30%", backtest_edge(oos, cfg, cfg["instruments"][sym], rules))


if __name__ == "__main__":
    main()
