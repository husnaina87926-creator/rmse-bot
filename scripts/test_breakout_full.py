"""Comprehensive test of the Donchian breakout edge vs the live all-weather momentum.
(1) Generalization: breakout on BTC/ETH/SOL (ret, CAGR, win, maxDD).
(2) Correlation: monthly P&L of breakout vs all-weather (uncorrelated => diversification).
(3) Portfolio: all-weather-only vs all-weather+breakout (combined CAGR + maxDD).
Both strategies: 4h, 10% risk, 20x cap, real fees, $5000 each. Run from project root.
"""
import sys, os, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.config import load_config
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.discovery import build_features
from rmse_bot.indicators import atr
from rmse_bot.regime import regime_mask

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
COST, RISK, LEV, START = 0.0005, 10.0, 20, 5000.0
cfg = load_config("config.yaml")
rf = cfg["regime_filter"]; EP, RN = rf["ema_period"], rf["rise_n"]


def _maxdd(times, pnls):
    bal = START; peak = START; mdd = 0.0; eq = []
    for t, p in zip(times, pnls):
        bal += p; peak = max(peak, bal); mdd = max(mdd, (peak - bal) / peak); eq.append((t, bal))
    return bal, mdd * 100, eq


def _monthly(times, pnls):
    s = pd.Series(pnls, index=pd.to_datetime(times))
    return s.resample("ME").sum()


def breakout(df, N=20, M=10, trendfilt=True):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    n = len(c)
    pH = pd.Series(h).rolling(N).max().shift(1).values
    pL = pd.Series(l).rolling(N).min().shift(1).values
    tH = pd.Series(h).rolling(M).max().shift(1).values
    tL = pd.Series(l).rolling(M).min().shift(1).values
    ema = df["close"].ewm(span=100, adjust=False).mean().values
    up = c > ema
    times = df["time"].values
    bal = START; tr_t = []; tr_p = []; i = N + 1; last = -1
    while i < n - 1:
        if i <= last or np.isnan(pH[i]) or np.isnan(tL[i]):
            i += 1; continue
        d = None
        if c[i] > pH[i] and c[i-1] <= pH[i] and (not trendfilt or up[i]):
            d, entry, stop, tch = "buy", c[i], tL[i], tL
        elif c[i] < pL[i] and c[i-1] >= pL[i] and (not trendfilt or not up[i]):
            d, entry, stop, tch = "sell", c[i], tH[i], tH
        if d is None:
            i += 1; continue
        rp = abs(entry - stop)
        if rp <= 0: i += 1; continue
        units = min((bal*RISK/100)/rp, (bal*LEV)/entry)
        exitp = None; j = i+1
        while j < n:
            if d == "buy" and l[j] <= tL[j]: exitp = tL[j]; break
            if d == "sell" and h[j] >= tH[j]: exitp = tH[j]; break
            j += 1
        if exitp is None: exitp = c[n-1]; j = n-1
        move = (exitp-entry) if d == "buy" else (entry-exitp)
        pnl = move*units - (entry+exitp)*units*COST
        bal += pnl; tr_t.append(times[j]); tr_p.append(pnl); last = j; i = j+1
    return tr_t, tr_p


def allweather(df, daily):
    feats = build_features(df); a = atr(df, cfg["risk"]["atr_period"]).values
    c = df["close"].values; times = df["time"].values
    dm = regime_mask(daily, EP, RN); dm = dm if isinstance(dm, np.ndarray) else dm.values
    dclose = daily["close"].values; ema = pd.Series(dclose).ewm(span=EP, adjust=False).mean().values
    dtimes = daily["time"].values
    def dreg(k):
        if k < EP: return None
        rising = ema[k] > ema[k-RN] if k >= RN else False
        if dclose[k] > ema[k] and rising: return "up"
        if dclose[k] < ema[k] and not rising: return "down"
        return None
    dregs = [dreg(k) for k in range(len(daily))]
    rules = [("sell","down",["rsi_bear","high_vol","strong_trend"]),
             ("buy","up",["rsi_overbought","high_vol","strong_trend"])]
    ex = cfg["crypto_rules"]["exit"]; sl_atr, rr, hold = ex["sl_atr"], ex["rr"], ex["max_hold"]
    bal = START; tr_t = []; tr_p = []; i = 250; j = 0; n = len(df)
    while i < n-1:
        while j+1 < len(dtimes) and dtimes[j+1] <= times[i]: j += 1
        cur = dregs[j] if dtimes[j] <= times[i] else None
        row = feats.iloc[i]; matched = None
        for d, reg, when in rules:
            if reg != cur: continue
            if all(bool(row[x]) for x in when): matched = (d, when); break
        if matched is None or np.isnan(a[i]) or a[i] == 0: i += 1; continue
        d, _ = matched; entry = float(c[i])
        if d == "buy": sl, tp = entry-sl_atr*a[i], entry+rr*sl_atr*a[i]
        else: sl, tp = entry+sl_atr*a[i], entry-rr*sl_atr*a[i]
        rp = abs(entry-sl); units = min((bal*RISK/100)/rp, (bal*LEV)/entry)
        fut = df.iloc[i+1:i+1+hold]
        if fut.empty: break
        out, ep2, ci = "time", float(fut["close"].iloc[-1]), min(i+hold, n-1)
        for k,(_,b) in enumerate(fut.iterrows()):
            if d == "buy":
                if b["low"] <= sl: ep2, ci = sl, i+1+k; break
                if b["high"] >= tp: ep2, ci = tp, i+1+k; break
            else:
                if b["high"] >= sl: ep2, ci = sl, i+1+k; break
                if b["low"] <= tp: ep2, ci = tp, i+1+k; break
        move = (ep2-entry) if d == "buy" else (entry-ep2)
        pnl = move*units - (entry+ep2)*units*COST
        bal += pnl; tr_t.append(times[ci]); tr_p.append(pnl); i = i+hold
    return tr_t, tr_p


def main():
    now = dt.datetime.now(dt.timezone.utc)
    print(f"4h | 10% risk | 20x cap | fees {COST*100:.2f}%/side | $5000 each\n")
    print(f"{'coin':9}{'STRAT':<11}{'trades':>7}{'win%':>6}{'final$':>9}{'CAGR':>8}{'maxDD':>7}")
    allm, brkm = {}, {}
    for sym in COINS:
        df = fetch_binance_klines(sym, "4h", now - dt.timedelta(days=2200), now)
        daily = fetch_binance_klines(sym, "1d", now - dt.timedelta(days=2200), now)
        yrs = (df["time"].iloc[-1]-df["time"].iloc[0]).days/365.25
        for name, fn in [("all-weather", lambda: allweather(df, daily)),
                         ("breakout", lambda: breakout(df))]:
            tt, tp = fn()
            fb, dd, _ = _maxdd(tt, tp)
            win = sum(1 for p in tp if p > 0)/len(tp)*100 if tp else 0
            cagr = ((fb/START)**(1/yrs)-1)*100 if fb > 0 else -100
            print(f"{sym:9}{name:<11}{len(tp):>7}{win:>5.0f}%{fb:>9.0f}{cagr:>+7.1f}%{dd:>6.0f}%")
            (allm if name == "all-weather" else brkm)[sym] = (tt, tp)
        # correlation (monthly)
        ma = _monthly(*allm[sym]); mb = _monthly(*brkm[sym])
        idx = ma.index.union(mb.index)
        corr = ma.reindex(idx, fill_value=0).corr(mb.reindex(idx, fill_value=0))
        print(f"{'':9}-> monthly corr (all-weather vs breakout): {corr:+.2f}")
    # PORTFOLIO: all coins, all-weather only  vs  all-weather + breakout
    print("\n=== PORTFOLIO (all 3 coins) ===")
    def combine(strats):
        tt, tp = [], []
        for sym in COINS:
            for s in strats:
                d = (allm if s == "aw" else brkm)[sym]
                tt += list(d[0]); tp += list(d[1])
        order = np.argsort(np.array(tt))
        tt = [tt[k] for k in order]; tp = [tp[k] for k in order]
        nacc = len(COINS)*len(strats)
        bal = START*nacc; peak = bal; mdd = 0
        for p in tp:
            bal += p; peak = max(peak, bal); mdd = max(mdd, (peak-bal)/peak)
        return bal, START*nacc, mdd*100
    yrs = 6.0
    for label, strats in [("all-weather only", ["aw"]), ("all-weather + breakout", ["aw","brk"])]:
        fb, st, dd = combine(strats)
        cagr = ((fb/st)**(1/yrs)-1)*100 if fb > 0 else -100
        print(f"  {label:<26} start ${st:,.0f} -> ${fb:,.0f}  CAGR {cagr:+.1f}%  maxDD {dd:.0f}%")


if __name__ == "__main__":
    main()
