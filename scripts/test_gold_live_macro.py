"""Does a REAL-YIELD filter improve our ACTUAL live gold edge (momentum + regime),
not just a daily breakout? Live rule: buy [trend_up & rsi_overbought & high_vol] in
daily up-regime. Test baseline vs + 'real yields falling' filter, on 1h gold 10yr
(long macro history), split-half. FRED DFII10 free. Fixed-risk additive, ~0.02% cost.
Run: python scripts/test_gold_live_macro.py
"""
import sys, os, urllib.request, io
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.discovery import build_features
from rmse_bot.indicators import atr as atr_fn

START, RISK, LEV, COST = 5000.0, 10.0, 50, 0.0001
SL_ATR, RR, HOLD = 2.0, 1.0, 24
EP, RN = 100, 20   # regime ema / rise lookback (config defaults)


def fred(series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    req = urllib.request.Request(url, headers={"User-Agent": "x"})
    txt = urllib.request.urlopen(req, timeout=25).read().decode()
    df = pd.read_csv(io.StringIO(txt)); df.columns = ["date", "val"]
    df["date"] = pd.to_datetime(df["date"]); df["val"] = pd.to_numeric(df["val"], errors="coerce")
    return df.dropna()


def main():
    g = pd.read_csv("data/XAUUSD_1h_10yr.csv", parse_dates=["time"])
    g["time"] = g["time"].dt.tz_localize(None)
    # daily regime
    daily = g.set_index("time").resample("1D").agg({"close": "last"}).dropna().reset_index()
    dc = daily["close"].values
    ema = pd.Series(dc).ewm(span=EP, adjust=False).mean().values
    up = np.zeros(len(daily), bool)
    for k in range(len(daily)):
        if k >= EP and k >= RN:
            up[k] = (dc[k] > ema[k]) and (ema[k] > ema[k-RN])
    dtimes = daily["time"].values
    # real yield aligned + 20d change
    ry_df = fred("DFII10")
    ryt = ry_df["date"].values; ryv = ry_df["val"].values
    didx = np.searchsorted(ryt, daily["time"].values, side="right") - 1
    ry_daily = np.where(didx >= 0, ryv[np.clip(didx, 0, len(ryv)-1)], np.nan)
    ry_chg = ry_daily - np.concatenate([np.full(20, np.nan), ry_daily[:-20]])  # 20d change per day

    # features on 1h
    df = g.rename(columns={}).reset_index(drop=True)
    feats = build_features(df); a = atr_fn(df, 14).values
    c = df["close"].values; h = df["high"].values; l = df["low"].values; times = df["time"].values
    n = len(df)
    # map each 1h bar -> daily index (regime + ry_chg)
    when = ["trend_up", "rsi_overbought", "high_vol"]

    def run(macro):
        bal = START; tt = []; tp = []; i = 250; j = 0
        while i < n-1:
            while j+1 < len(dtimes) and dtimes[j+1] <= times[i]: j += 1
            if not up[j]:                       # daily up-regime (current live filter)
                i += 1; continue
            if macro and not (not np.isnan(ry_chg[j]) and ry_chg[j] < 0):  # real yields falling
                i += 1; continue
            row = feats.iloc[i]
            if not all(bool(row[x]) for x in when) or np.isnan(a[i]) or a[i] == 0:
                i += 1; continue
            entry = float(c[i]); sl = entry - SL_ATR*a[i]; tp_ = entry + RR*SL_ATR*a[i]
            rp = abs(entry-sl)
            if rp < entry*0.0005: i += 1; continue
            units = min((START*RISK/100)/rp, (START*LEV)/entry)
            fut = df.iloc[i+1:i+1+HOLD]
            if fut.empty: break
            ep2, ci = float(fut["close"].iloc[-1]), min(i+HOLD, n-1)
            for k,(_,b) in enumerate(fut.iterrows()):
                if b["low"] <= sl: ep2, ci = sl, i+1+k; break
                if b["high"] >= tp_: ep2, ci = tp_, i+1+k; break
            pnl = (ep2-entry)*units - (entry+ep2)*units*COST
            bal += pnl; tt.append(times[ci]); tp.append(pnl); i = i+HOLD
        if not tp: return None
        peak = START; rb = START; mdd = 0
        for p in tp: rb += p; peak = max(peak, rb); mdd = max(mdd, (peak-rb)/peak)
        mid = times[len(times)//2]
        b1 = START + sum(p for t, p in zip(tt, tp) if t < mid)
        b2 = START + sum(p for t, p in zip(tt, tp) if t >= mid)
        win = sum(1 for p in tp if p > 0)/len(tp)*100
        return bal, len(tp), win, mdd*100, b1, b2

    yrs = (df["time"].iloc[-1]-df["time"].iloc[0]).days/365.25
    print(f"LIVE gold edge (momentum+regime) +/- real-yield filter | 1h {yrs:.1f}yr | split-half\n")
    print(f"  {'variant':<40}{'trades':>7}{'win%':>6}{'final$':>9}{'P&L':>9}{'DD':>5}{'1st':>9}{'2nd':>9}{'rob':>5}")
    for nm, macro in [("baseline (price-regime only)", False), ("+ real yields falling filter", True)]:
        r = run(macro)
        if r is None: print(f"  {nm:<40} (no trades)"); continue
        bal, ntr, win, dd, b1, b2 = r
        rob = "YES" if (bal > START and b1 > START and b2 > START) else ""
        print(f"  {nm:<40}{ntr:>7}{win:>5.0f}%{bal:>9.0f}{bal-START:>+9.0f}{dd:>4.0f}%"
              f"{('$'+format(b1,'.0f')):>9}{('$'+format(b2,'.0f')):>9}{rob:>5}")


if __name__ == "__main__":
    main()
