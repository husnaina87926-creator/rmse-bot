"""Discover each new coin's OWN best strategy (not BTC/ETH's), the same way we built
BTC/ETH: self-generate walk-forward-robust entries x exit grid, backtest with realistic
crypto fees, rank by ROBUST profit (return x consistency across time windows). Then also
test the top pick WITH the daily-regime filter to see if our regime filter helps.
Run from project root:  python scripts/discover_new_coins.py
"""
import sys, os, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.strategy_generator import generate_strategies, evaluate_strategy
from rmse_bot.backtest import backtest_edge
from rmse_bot.regime import regime_mask

COINS = ["BNBUSDT", "SOLUSDT", "XRPUSDT"]


def main():
    cfg = load_config("config.yaml")
    now = dt.datetime.now(dt.timezone.utc)
    for sym in COINS:
        print("=" * 70)
        try:
            df = fetch_binance_klines(sym, "4h", now - dt.timedelta(days=3650), now)
        except Exception as e:
            print(f"{sym}: fetch failed {e}"); continue
        if len(df) < 1000:
            print(f"{sym}: too little data ({len(df)})"); continue
        med = float(df["close"].median())
        # realistic Binance cost ~0.25% round-trip, expressed in price units at median price
        cfg["instruments"][sym] = {"contract_size": 1, "spread_price": 0.00125 * med,
                                   "slippage_price": 0.00125 * med,
                                   "commission_per_lot": 0.0, "swap_per_lot": 0.0}
        yrs = (df["time"].iloc[-1] - df["time"].iloc[0]).days / 365.25
        print(f"{sym}  {yrs:.1f}yr  {len(df)} 4h-bars  med price ${med:,.2f}  cost~0.25%/trade")

        board = generate_strategies(df, cfg, sym, max_entries=8, min_count=150)
        if not board:
            print("  no strategy reached min trades — NOTHING WORKS\n"); continue
        by_ret = sorted(board, key=lambda x: x["return"], reverse=True)   # best by raw profit
        print(f"  BEST BY PROFIT:")
        print(f"  {'#':<2}{'dir':<5}{'entry':<42}{'ret$':>9}{'PF':>6}{'win':>6}{'cons':>6}{'tr':>5}")
        for i, s in enumerate(by_ret[:4]):
            ent = " & ".join(s["entry"])[:40]
            print(f"  {i+1:<2}{s['direction']:<5}{ent:<42}{s['return']:>9.0f}{s['pf']:>6.2f}"
                  f"{s['win']*100:>5.0f}%{s['consistency']*100:>5.0f}%{s['trades']:>5}")

        # top pick + regime filter (only trade when 4h-EMA regime agrees with direction)
        top = by_ret[0]
        instr = cfg["instruments"][sym]
        rmask = regime_mask(df, cfg["regime_filter"]["ema_period"], cfg["regime_filter"]["rise_n"])
        if top["direction"] == "sell":
            rmask = ~rmask  # shorts only in down-regime
        ex = {"sl_atr": 2.0, "rr": top["exit"]["rr"], "max_hold": top["exit"]["hold"],
              "be_atr": top["exit"]["be"]}
        res = backtest_edge(df, cfg, instr, [{"direction": top["direction"], "when": top["entry"]}],
                            regime_mask=rmask, **ex)
        m = res.metrics
        print(f"  -> BEST + regime filter: ret ${m['total_return']:.0f}  PF {m['profit_factor']:.2f}"
              f"  win {m['win_rate']*100:.0f}%  trades {m['num_trades']}")
        print()


if __name__ == "__main__":
    main()
