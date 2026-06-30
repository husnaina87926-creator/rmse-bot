"""Round 2 frequent-edge hunt: long-biased trend strategies (crypto has a bull bias,
so frequent SHORTS got slaughtered in round 1). Families: EMA-pullback bounce,
momentum continuation, regime-aware dip-buy/rip-fade. Adds a profit-target exit so
high-win-rate setups actually bank gains. Realistic fees + leverage cap.
Run: python scripts/hunt_frequent2.py <tf> <days>   (default 1h 1400)
"""
import sys, os, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.indicators import atr as atr_fn

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
COST, LEV, START, RISK = 0.0005, 20, 5000.0, 5.0


def rsi(close, p):
    d = np.diff(close, prepend=close[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ag = pd.Series(up).ewm(alpha=1/p, adjust=False).mean().values
    al = pd.Series(dn).ewm(alpha=1/p, adjust=False).mean().values
    rs = np.divide(ag, al, out=np.full_like(ag, np.inf), where=al != 0)
    return 100 - 100/(1+rs)


def bt(df, ent_l, ent_s, atr_arr, sl_atr, tp_atr, exit_l, exit_s, max_hold):
    c = df["close"].values; h = df["high"].values; l = df["low"].values; n = len(c)
    bal = START; tr = []; i = 210; peak = START; mdd = 0.0
    while i < n - 1:
        go = "buy" if ent_l[i] else ("sell" if ent_s[i] else None)
        if go is None or np.isnan(atr_arr[i]) or atr_arr[i] == 0:
            i += 1; continue
        entry = c[i]; A = atr_arr[i]
        sl = entry - sl_atr*A if go == "buy" else entry + sl_atr*A
        tp = entry + tp_atr*A if go == "buy" else entry - tp_atr*A
        rp = abs(entry - sl)
        if rp <= 0: i += 1; continue
        units = min((bal*RISK/100)/rp, (bal*LEV)/entry)
        exitp = None; j = i + 1; end = min(i + max_hold, n - 1)
        while j <= end:
            if go == "buy":
                if l[j] <= sl: exitp = sl; break
                if h[j] >= tp: exitp = tp; break
                if exit_l[j]: exitp = c[j]; break
            else:
                if h[j] >= sl: exitp = sl; break
                if l[j] <= tp: exitp = tp; break
                if exit_s[j]: exitp = c[j]; break
            j += 1
        if exitp is None: exitp = c[end]; j = end
        move = (exitp - entry) if go == "buy" else (entry - exitp)
        pnl = move*units - (entry + exitp)*units*COST
        bal += pnl; tr.append(pnl); peak = max(peak, bal); mdd = max(mdd, (peak-bal)/peak)
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
        days = (df["time"].iloc[-1]-df["time"].iloc[0]).days; yrs = days/365.25
        c = df["close"].values; a = atr_fn(df, 14).values
        ema200 = pd.Series(c).ewm(span=200, adjust=False).mean().values
        ema50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
        ema20 = pd.Series(c).ewm(span=20, adjust=False).mean().values
        r14 = rsi(c, 14); r2 = rsi(c, 2)
        up = c > ema200; dn = c < ema200
        prevc = np.roll(c, 1)
        pH10 = pd.Series(df["high"].values).rolling(10).max().shift(1).values
        pH20 = pd.Series(df["high"].values).rolling(20).max().shift(1).values
        T = np.ones(len(c), dtype=bool); F = np.zeros(len(c), dtype=bool)
        print(f"\n===== {sym} {TF} ({yrs:.1f}yr) =====")
        print(f"  {'strategy':<38}{'tr/day':>7}{'win%':>6}{'final$':>9}{'CAGR':>8}{'maxDD':>7}")
        configs = [
            # EMA pullback bounce (cross back above fast EMA in uptrend)
            ("ema20 pullback-bounce up-only", up & (c > ema20) & (prevc <= ema20), F, 2.0, 3.0, c < ema20, F, 24),
            ("ema50 pullback-bounce up-only", up & (c > ema50) & (prevc <= ema50), F, 2.5, 3.0, c < ema50, F, 36),
            # momentum continuation in uptrend
            ("mom-cont >10H up-only", up & (c > pH10) & (prevc <= pH10), F, 2.0, 4.0, F, F, 24),
            ("mom-cont >20H up-only", up & (c > pH20) & (prevc <= pH20), F, 2.0, 4.0, F, F, 36),
            # dip-buy in uptrend / rip-fade in downtrend (regime-aware reversion + target)
            ("RSI2 dip-buy up / rip-fade dn", up & (r2 < 10), dn & (r2 > 90), 2.5, 2.0, r14 > 55, r14 < 45, 24),
            ("RSI14<35 dip-buy up-only +tp", up & (r14 < 35) & (prevc <= c), F, 2.5, 2.5, r14 > 55, F, 24),
            ("RSI2<15 dip-buy up-only +tp", up & (r2 < 15), F, 2.5, 2.0, r14 > 55, F, 18),
            # tighter target scalps (more frequent banking)
            ("ema20 bounce up, tp1.0", up & (c > ema20) & (prevc <= ema20), F, 1.5, 1.0, F, F, 12),
            ("RSI2<10 dip up, tp1.0", up & (r2 < 10), F, 1.5, 1.0, F, F, 12),
        ]
        for nm, el, es, sl, tp, xl, xs, mh in configs:
            el = np.asarray(el) & ~np.isnan(a) & ~np.isnan(ema200)
            es = np.asarray(es) & ~np.isnan(a) & ~np.isnan(ema200)
            xl = np.asarray(xl) if not np.isscalar(xl) else (T if xl else F)
            xs = np.asarray(xs) if not np.isscalar(xs) else (T if xs else F)
            fb, tr, dd = bt(df, el, es, a, sl, tp, xl, xs, mh)
            if not tr:
                print(f"  {nm:<38}{'(no trades)':>7}"); continue
            tpd = len(tr)/days; win = sum(1 for t in tr if t > 0)/len(tr)*100
            cagr = ((fb/START)**(1/yrs)-1)*100 if fb > 0 else -100
            flag = "  <== HIT" if (tpd >= 0.7 and fb > START) else ""
            if flag: hits.append((sym, nm, tpd, win, cagr, dd))
            print(f"  {nm:<38}{tpd:>7.2f}{win:>5.0f}%{fb:>9.0f}{cagr:>+7.1f}%{dd:>6.0f}%{flag}")
    print("\n"+"="*60)
    if hits:
        print(f"FOUND {len(hits)} >=0.7 tr/day AND net-positive:")
        for sym, nm, tpd, win, cagr, dd in sorted(hits, key=lambda x: x[4], reverse=True):
            print(f"  {sym} | {nm} | {tpd:.2f}/day | win {win:.0f}% | CAGR {cagr:+.1f}% | DD {dd:.0f}%")
    else:
        print("NO config met >=0.7 trades/day AND net-positive this round.")


if __name__ == "__main__":
    main()
