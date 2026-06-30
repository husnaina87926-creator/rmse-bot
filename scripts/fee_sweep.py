"""Fee-sensitivity sweep for the mean-reversion edge (it's strongly +EV at zero fee;
question is whether it survives REAL fees). For top RSI-2 configs on BTC/ETH/SOL,
sweep per-side fee and show final$ at each. Realistic refs: Binance FUTURES maker
~0.02%/side (0.018% with BNB) = the natural execution for limit dip-buys; taker 0.05%.
Run: python scripts/fee_sweep.py
"""
import os, sys, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.indicators import atr as atr_fn

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
LEV, START, RISK = 20, 5000.0, 5.0
FEES = [0.0, 0.0001, 0.00015, 0.0002, 0.00025, 0.0003, 0.0004, 0.0005]   # per side


def rsi(c, p):
    d = np.diff(c, prepend=c[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ag = pd.Series(up).ewm(alpha=1/p, adjust=False).mean().values
    al = pd.Series(dn).ewm(alpha=1/p, adjust=False).mean().values
    rs = np.divide(ag, al, out=np.full_like(ag, np.inf), where=al != 0)
    return 100 - 100/(1+rs)


def run(df, el, es, xl, xs, a, cost, sl_atr=3.0, max_hold=24):
    c = df["close"].values; h = df["high"].values; l = df["low"].values; n = len(c)
    bal = START; tr = []; i = 210; peak = START; mdd = 0.0
    while i < n - 1:
        go = "buy" if el[i] else ("sell" if es[i] else None)
        if go is None or np.isnan(a[i]) or a[i] == 0:
            i += 1; continue
        entry = c[i]; sl = entry - sl_atr*a[i] if go == "buy" else entry + sl_atr*a[i]
        rp = abs(entry - sl)
        if rp <= 0: i += 1; continue
        units = min((bal*RISK/100)/rp, (bal*LEV)/entry)
        exitp = None; j = i + 1; end = min(i + max_hold, n - 1)
        while j <= end:
            if go == "buy":
                if l[j] <= sl: exitp = sl; break
                if xl[j]: exitp = c[j]; break
            else:
                if h[j] >= sl: exitp = sl; break
                if xs[j]: exitp = c[j]; break
            j += 1
        if exitp is None: exitp = c[end]; j = end
        move = (exitp - entry) if go == "buy" else (entry - exitp)
        pnl = move*units - (entry + exitp)*units*cost
        bal += pnl; tr.append(pnl); peak = max(peak, bal); mdd = max(mdd, (peak-bal)/peak)
        if bal <= 0: break
        i = j + 1
    return bal, len(tr), (sum(1 for t in tr if t > 0)/len(tr)*100 if tr else 0), mdd*100


def main():
    now = dt.datetime.now(dt.timezone.utc)
    print("Mean-reversion fee sensitivity | 1h | 5% risk | 20x | final$ at each per-side fee")
    print("realistic: futures maker ~0.0002 (0.018 w/BNB) | taker ~0.0005\n")
    hdr = "coin/config".ljust(30) + "tr/day".rjust(7) + "win%".rjust(6) + "".join(f"{f*100:.3f}%".rjust(9) for f in FEES)
    for sym in COINS:
        df = fetch_binance_klines(sym, "1h", now - dt.timedelta(days=1400), now)
        days = (df["time"].iloc[-1]-df["time"].iloc[0]).days
        c = df["close"].values; a = atr_fn(df, 14).values
        sma200 = pd.Series(c).rolling(200).mean().values
        r2 = rsi(c, 2); r3 = rsi(c, 3); r4 = rsi(c, 4)
        up = c > sma200; dn = c < sma200
        configs = {
            "RSI2<15 filt both": ((r2 < 15) & up, (r2 > 85) & dn, r2 > 50, r2 < 50),
            "RSI2<10 filt both": ((r2 < 10) & up, (r2 > 90) & dn, r2 > 50, r2 < 50),
            "RSI2<15 filt L": ((r2 < 15) & up, np.zeros(len(c), bool), r2 > 50, np.zeros(len(c), bool)),
            "RSI3<15 filt L": ((r3 < 15) & up, np.zeros(len(c), bool), r3 > 55, np.zeros(len(c), bool)),
            "RSI4<20 filt L": ((r4 < 20) & up, np.zeros(len(c), bool), r4 > 55, np.zeros(len(c), bool)),
        }
        print(f"===== {sym} ({days}d) =====")
        print(hdr)
        for nm, (el, es, xl, xs) in configs.items():
            el = np.asarray(el) & ~np.isnan(a) & ~np.isnan(sma200)
            es = np.asarray(es) & ~np.isnan(a) & ~np.isnan(sma200)
            finals = []; tpd = win = 0
            for fee in FEES:
                fb, n, w, dd = run(df, el, es, xl, xs, a, fee)
                finals.append(fb)
                if fee == FEES[0]: tpd, win = n/days, w
            row = f"{nm:<30}{tpd:>7.2f}{win:>5.0f}%"
            for fb in finals:
                mark = "+" if fb > START else " "
                row += f"{fb:>8.0f}{mark}"
            print(row)
        print()


if __name__ == "__main__":
    main()
