"""Test gold-on-crypto: does our gold strategy work on PAXG (tokenized gold) on Binance?
(1) Apply gold's EXACT live rule + regime + exit to PAXG. (2) Discover PAXG's own best.
PAXG is low-volume vs BTC -> conservative cost. Run: python scripts/test_paxg.py
"""
import sys, os, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.config import load_config
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.backtest import backtest_edge
from rmse_bot.regime import regime_mask
from rmse_bot.strategy_generator import generate_strategies, robustness_consistency

SYM = "PAXGUSDT"
cfg = load_config("config.yaml")
now = dt.datetime.now(dt.timezone.utc)
rf = cfg["regime_filter"]; ep, rn = rf["ema_period"], rf["rise_n"]

df = fetch_binance_klines(SYM, "15m", now - dt.timedelta(days=540), now)
daily = fetch_binance_klines(SYM, "1d", now - dt.timedelta(days=900), now)
px = float(df["close"].iloc[-1]); med = float(df["close"].median())
yrs = (df["time"].iloc[-1] - df["time"].iloc[0]).days / 365.25
# conservative cost for low-liquidity PAXG: ~0.15% each side at median price
cost = 0.0015 * med
cfg["instruments"][SYM] = {"contract_size": 1, "spread_price": cost, "slippage_price": cost,
                           "commission_per_lot": 0.0, "swap_per_lot": 0.0}
print(f"{SYM}: {len(df)} 15m-bars, {yrs:.2f}yr, cur ${px:,.2f}, cost ~0.3% round")

# regime mask from DAILY (align to 15m by forward-fill on time)
import pandas as pd, numpy as np
dmask = regime_mask(daily, ep, rn)
dvals = dmask if isinstance(dmask, np.ndarray) else dmask.values
# map each 15m bar to most recent daily regime-up bool
reg15 = []
times = df["time"].values; dtimes = daily["time"].values
j = 0
for t in times:
    while j + 1 < len(dtimes) and dtimes[j + 1] <= t:
        j += 1
    reg15.append(bool(dvals[j]) if dtimes[j] <= t else False)
reg15 = np.array(reg15)

# (1) GOLD's exact live rule on PAXG
gold_rule = cfg["edge_rules"]["XAUUSD"]
ex = {"sl_atr": 2.0, "rr": 1.0, "max_hold": 24, "be_atr": 1.0}
res = backtest_edge(df, cfg, cfg["instruments"][SYM],
                    [{"direction": "buy", "when": gold_rule[0]["when"]}], regime_mask=reg15, **ex)
m = res.metrics
print(f"\n[1] GOLD's rule on PAXG (buy trend_up&rsi_overbought&high_vol, regime up):")
print(f"    ret ${m['total_return']:.0f}  PF {m['profit_factor']:.2f}  win {m['win_rate']*100:.0f}%  trades {m['num_trades']}")

# (2) discover PAXG's OWN best strategy
print(f"\n[2] PAXG's OWN discovered strategies (15m, walk-forward + fees):")
board = generate_strategies(df, cfg, SYM, max_entries=8, min_count=120)
if not board:
    print("    no strategy reached min trades")
else:
    by_ret = sorted(board, key=lambda x: x["return"], reverse=True)
    print(f"    {'dir':<5}{'entry':<40}{'ret$':>9}{'PF':>6}{'win':>6}{'cons':>6}{'tr':>5}")
    for s in by_ret[:5]:
        print(f"    {s['direction']:<5}{' & '.join(s['entry'])[:38]:<40}{s['return']:>9.0f}"
              f"{s['pf']:>6.2f}{s['win']*100:>5.0f}%{s['consistency']*100:>5.0f}%{s['trades']:>5}")
