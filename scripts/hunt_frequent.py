"""Hunt for a HIGH-FREQUENCY (>=~1 trade/day) edge that is net-profitable after fees,
on BTC/ETH/SOL. Round 1 = mean-reversion family (RSI-2, Bollinger fade, z-score),
which trades often and is naturally uncorrelated with our momentum all-weather.

Honest sizing: realistic Binance fees, leverage cap, risk-based size. Reports every
config; flags those with >=0.7 trades/day AND positive net. Goal = find positive
expectancy first; leverage can amplify a real edge afterwards.
Run:  python scripts/hunt_frequent.py <tf> <days>     (default 1h 1400)
"""
import sys, os, datetime as dt, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.indicators import atr as atr_fn

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
COST = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0005   # per-side; arg3 to test maker/zero
LEV, START = 20, 5000.0
RISK = 5.0


def rsi(close, period):
    d = np.diff(close, prepend=close[0])
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ag = pd.Series(up).ewm(alpha=1/period, adjust=False).mean().values
    al = pd.Series(dn).ewm(alpha=1/period, adjust=False).mean().values
    rs = np.divide(ag, al, out=np.full_like(ag, np.inf), where=al != 0)
    return 100 - 100/(1+rs)


def backtest(df, entry_long, entry_short, exit_long, exit_short, atr_arr,
             sl_atr=3.0, max_hold=24, direction="both"):
    c = df["close"].values; h = df["high"].values; l = df["low"].values
    times = df["time"].values; n = len(c)
    bal = START; tr = []; i = 50; peak = START; mdd = 0.0
    while i < n - 1:
        go = None
        if direction in ("L", "both") and entry_long[i]: go = "buy"
        elif direction in ("S", "both") and entry_short[i]: go = "sell"
        if go is None or np.isnan(atr_arr[i]) or atr_arr[i] == 0:
            i += 1; continue
        entry = c[i]
        sl = entry - sl_atr*atr_arr[i] if go == "buy" else entry + sl_atr*atr_arr[i]
        rp = abs(entry - sl)
        if rp <= 0: i += 1; continue
        units = min((bal*RISK/100)/rp, (bal*LEV)/entry)
        exitp = None; j = i + 1; end = min(i + max_hold, n - 1)
        while j <= end:
            if go == "buy":
                if l[j] <= sl: exitp = sl; break
                if exit_long[j]: exitp = c[j]; break
            else:
                if h[j] >= sl: exitp = sl; break
                if exit_short[j]: exitp = c[j]; break
            j += 1
        if exitp is None: exitp = c[end]; j = end
        move = (exitp - entry) if go == "buy" else (entry - exitp)
        pnl = move*units - (entry + exitp)*units*COST
        bal += pnl; tr.append(pnl)
        peak = max(peak, bal); mdd = max(mdd, (peak - bal)/peak)
        if bal <= 0: break
        i = j + 1
    return bal, tr, mdd*100


def main():
    now = dt.datetime.now(dt.timezone.utc)
    TF = sys.argv[1] if len(sys.argv) > 1 else "1h"
    DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 1400
    hits = []
    for sym in COINS:
        df = fetch_binance_klines(sym, TF, now - dt.timedelta(days=DAYS), now)
        days = (df["time"].iloc[-1] - df["time"].iloc[0]).days
        yrs = days/365.25
        c = df["close"].values
        a = atr_fn(df, 14).values
        sma200 = pd.Series(c).rolling(200).mean().values
        ma5 = pd.Series(c).rolling(5).mean().values
        # indicators
        r2 = rsi(c, 2); r3 = rsi(c, 3); r4 = rsi(c, 4)
        bb_mid = pd.Series(c).rolling(20).mean().values
        bb_std = pd.Series(c).rolling(20).std().values
        z = (c - bb_mid)/np.where(bb_std == 0, np.nan, bb_std)
        print(f"\n===== {sym} {TF} ({yrs:.1f}yr, {days}d) =====")
        print(f"  {'strategy':<34}{'tr/day':>7}{'win%':>6}{'final$':>9}{'CAGR':>8}{'maxDD':>7}")
        configs = []
        # RSI-2 mean reversion, various thresholds, with/without uptrend filter, dir
        for (rp, ros, rex) in [(r2,10,50),(r2,5,60),(r2,15,50),(r3,15,55),(r4,20,55)]:
            for filt in [False, True]:
                for direction in ["L", "both"]:
                    el = (rp < ros) & ((c > sma200) if filt else True)
                    es = (rp > (100-ros)) & ((c < sma200) if filt else True)
                    xl = rp > rex; xs = rp < (100-rex)
                    nm = f"RSI{ '2' if rp is r2 else ('3' if rp is r3 else '4')}<{ros} exit>{rex}{' filt' if filt else ''} {direction}"
                    configs.append((nm, el, es, xl, xs, "L" if direction == "L" else "both"))
        # Bollinger / z-score fade
        for zt in [1.5, 2.0, 2.5]:
            for direction in ["L", "both"]:
                el = z < -zt; es = z > zt
                xl = c > ma5; xs = c < ma5
                configs.append((f"z-fade |z|>{zt} exit->ma5 {direction}", el, es, xl, xs,
                                "L" if direction == "L" else "both"))
        for nm, el, es, xl, xs, direction in configs:
            el = np.asarray(el) & ~np.isnan(a); es = np.asarray(es) & ~np.isnan(a)
            fb, tr, dd = backtest(df, el, es, xl, xs, a, direction=direction)
            if not tr:
                continue
            tpd = len(tr)/days; win = sum(1 for t in tr if t > 0)/len(tr)*100
            cagr = ((fb/START)**(1/yrs)-1)*100 if fb > 0 else -100
            flag = ""
            if tpd >= 0.7 and fb > START: flag = "  <== HIT"
            if tpd >= 0.7 and fb > START: hits.append((sym, nm, tpd, win, cagr, dd))
            print(f"  {nm:<34}{tpd:>7.2f}{win:>5.0f}%{fb:>9.0f}{cagr:>+7.1f}%{dd:>6.0f}%{flag}")
    print("\n" + "="*60)
    if hits:
        print(f"FOUND {len(hits)} config(s) with >=0.7 trades/day AND net-positive:")
        for sym, nm, tpd, win, cagr, dd in sorted(hits, key=lambda x: x[4], reverse=True):
            print(f"  {sym} | {nm} | {tpd:.2f} tr/day | win {win:.0f}% | CAGR {cagr:+.1f}% | DD {dd:.0f}%")
    else:
        print("NO config met >=0.7 trades/day AND net-positive in this round.")


if __name__ == "__main__":
    main()
