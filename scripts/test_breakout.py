"""Donchian / Turtle breakout test (the 'continuation' edge, done properly).

Entry: close breaks the prior-N high (long) / prior-N low (short) = breakout.
Exit:  Donchian TRAILING stop — exit long when price hits the prior-M low (M<N),
       short when it hits prior-M high. This lets winners RUN (the whole point of
       trend-following) instead of capping them with a fixed RR.
Realistic Binance fees, 20x leverage cap, 1% risk/trade. Optional EMA trend filter.
Run:  python scripts/test_breakout.py <tf> <days>   e.g. python scripts/test_breakout.py 4h 2000
"""
import sys, os, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.binance_feed import fetch_binance_klines

SYM = "BTCUSDT"
COST = 0.0005          # 0.05%/side
RISK = 0.01            # 1% risk/trade
START = 5000.0
LEVERAGE = 20
MAX_HOLD = 99999       # trend-follow: hold until the trailing stop, not a time cap


def rolling_prior_max(a, N):
    out = np.full(len(a), np.nan)
    for i in range(N, len(a)):
        out[i] = a[i - N:i].max()
    return out


def rolling_prior_min(a, N):
    out = np.full(len(a), np.nan)
    for i in range(N, len(a)):
        out[i] = a[i - N:i].min()
    return out


def backtest(o, h, l, c, N, M, direction, trend=None):
    n = len(c)
    pH = rolling_prior_max(h, N); pL = rolling_prior_min(l, N)
    tH = rolling_prior_max(h, M); tL = rolling_prior_min(l, M)   # trailing channels
    bal = START; trades = []; i = N + 1; last = -1
    while i < n - 1:
        if i <= last or np.isnan(pH[i]) or np.isnan(tL[i]):
            i += 1; continue
        d = None
        if direction in ("L", "both") and c[i] > pH[i] and c[i - 1] <= pH[i]:
            if trend is None or trend[i]:
                d, entry, stop = "buy", c[i], tL[i]
        if d is None and direction in ("S", "both") and c[i] < pL[i] and c[i - 1] >= pL[i]:
            if trend is None or (not trend[i]):
                d, entry, stop = "sell", c[i], tH[i]
        if d is None:
            i += 1; continue
        risk_per = abs(entry - stop)
        if risk_per <= 0:
            i += 1; continue
        units = min((bal * RISK) / risk_per, (bal * LEVERAGE) / entry)
        exitp = None; j = i + 1
        while j < min(i + MAX_HOLD, n):
            if d == "buy":
                if l[j] <= tL[j]: exitp = tL[j]; break       # trailing Donchian stop
            else:
                if h[j] >= tH[j]: exitp = tH[j]; break
            j += 1
        if exitp is None:
            exitp = c[min(j, n - 1)]
        move = (exitp - entry) if d == "buy" else (entry - exitp)
        pnl = move * units - (entry + exitp) * units * COST
        bal += pnl; trades.append(pnl); last = j
        if bal <= 0: break
        i = j + 1
    if not trades:
        return None
    wins = sum(1 for t in trades if t > 0)
    return {"n": len(trades), "win": wins / len(trades), "final": bal, "ret": bal - START}


def main():
    now = dt.datetime.now(dt.timezone.utc)
    TF = sys.argv[1] if len(sys.argv) > 1 else "4h"
    DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    df = fetch_binance_klines(SYM, TF, now - dt.timedelta(days=DAYS), now)
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    days = (df["time"].iloc[-1] - df["time"].iloc[0]).days
    yrs = days / 365.25
    ema = df["close"].ewm(span=100, adjust=False).mean().values
    trend = c > ema
    print(f"{SYM} {TF}: {len(df)} bars, {yrs:.1f}yr, Donchian breakout + trailing exit, fees {COST*100:.2f}%/side\n")
    print(f"{'breakout/exit':<26}{'dir':<6}{'trades':>7}{'win%':>6}{'final$':>10}{'P&L':>9}{'CAGR':>8}")
    configs = [
        ("N20/M10 (Turtle-1)", 20, 10, "both", None),
        ("N20/M10 long-only", 20, 10, "L", None),
        ("N55/M20 (Turtle-2)", 55, 20, "both", None),
        ("N55/M20 long-only", 55, 20, "L", None),
        ("N20/M10 + trend filt", 20, 10, "both", trend),
        ("N10/M5 (fast)", 10, 5, "both", None),
        ("N40/M20", 40, 20, "both", None),
    ]
    pos = 0
    for name, N, M, d, tr in configs:
        r = backtest(o, h, l, c, N, M, d, tr)
        if r is None:
            print(f"{name:<26}{d:<6}{'(no trades)':>7}"); continue
        cagr = ((r["final"] / START) ** (1 / yrs) - 1) * 100 if r["final"] > 0 and yrs > 0 else -100
        flag = "POS" if r["ret"] > 0 else "neg"
        if r["ret"] > 0: pos += 1
        print(f"{name:<26}{d:<6}{r['n']:>7}{r['win']*100:>5.0f}%{r['final']:>10.0f}{r['ret']:>+9.0f}{cagr:>+7.1f}%  [{flag}]")
    print(f"\n=> {len(configs)} configs, {pos} positive after fees")


if __name__ == "__main__":
    main()
