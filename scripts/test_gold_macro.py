"""Does MACRO (real yields + dollar) improve a gold strategy? Test baseline gold
breakout vs macro-filtered variants, split-half robustness. Real yields (FRED DFII10)
and broad dollar (FRED DTWEXBGS) are free, no key. Hypothesis (research): gold rises
when real yields fall (-0.82 corr) and dollar falls. So gate gold longs to falling-yield
regimes. Fixed-risk additive backtest, ~0.02% round cost. Run: python scripts/test_gold_macro.py
"""
import sys, os, urllib.request, io
import numpy as np, pandas as pd

START, RISK, LEV, COST = 5000.0, 10.0, 50, 0.0001   # 0.01%/side gold


def fred(series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    req = urllib.request.Request(url, headers={"User-Agent": "x"})
    txt = urllib.request.urlopen(req, timeout=25).read().decode()
    df = pd.read_csv(io.StringIO(txt))
    df.columns = ["date", "val"]
    df["date"] = pd.to_datetime(df["date"])
    df["val"] = pd.to_numeric(df["val"], errors="coerce")
    return df.dropna()


def load_gold_daily():
    g = pd.read_csv("data/XAUUSD_1h_10yr.csv", parse_dates=["time"])
    g = g.set_index("time")
    d = g.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    d = d.reset_index().rename(columns={"time": "date"})
    d["date"] = d["date"].dt.tz_localize(None)
    return d


def align(dates, macro):
    """most-recent macro value as of each gold date (forward-fill)."""
    mt = macro["date"].values; mv = macro["val"].values
    idx = np.searchsorted(mt, dates.values, side="right") - 1
    out = np.where(idx >= 0, mv[np.clip(idx, 0, len(mv)-1)], np.nan)
    return out


def backtest(d, gate, N=20, M=10):
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    n = len(c)
    pH = pd.Series(h).rolling(N).max().shift(1).values
    pL = pd.Series(l).rolling(N).min().shift(1).values
    tH = pd.Series(h).rolling(M).max().shift(1).values
    tL = pd.Series(l).rolling(M).min().shift(1).values
    times = d["date"].values
    bal = START; tt = []; tp = []; i = N+1; last = -1
    while i < n-1:
        if i <= last or np.isnan(pH[i]) or np.isnan(tL[i]):
            i += 1; continue
        dr = None
        if c[i] > pH[i] and c[i-1] <= pH[i]: dr, stop = "buy", tL[i]
        elif c[i] < pL[i] and c[i-1] >= pL[i]: dr, stop = "sell", tH[i]
        if dr is None or (gate is not None and not gate(dr, i)):
            i += 1; continue
        entry = c[i]; rp = abs(entry-stop)
        if rp < entry*0.001: i += 1; continue
        units = min((START*RISK/100)/rp, (START*LEV)/entry)
        exitp = None; j = i+1
        while j < n:
            if dr == "buy" and l[j] <= tL[j]: exitp = tL[j]; break
            if dr == "sell" and h[j] >= tH[j]: exitp = tH[j]; break
            j += 1
        if exitp is None: exitp = c[n-1]; j = n-1
        move = (exitp-entry) if dr == "buy" else (entry-exitp)
        pnl = move*units - (entry+exitp)*units*COST
        bal += pnl; tt.append(times[j]); tp.append(pnl); last = j; i = j+1
    if not tp: return None
    peak = START; run = START; mdd = 0
    for p in tp: run += p; peak = max(peak, run); mdd = max(mdd, (peak-run)/peak)
    mid = times[len(times)//2]
    b1 = START + sum(p for t, p in zip(tt, tp) if t < mid)
    b2 = START + sum(p for t, p in zip(tt, tp) if t >= mid)
    win = sum(1 for p in tp if p > 0)/len(tp)*100
    return bal, len(tp), win, mdd*100, b1, b2


def main():
    d = load_gold_daily()
    ry = align(d["date"], fred("DFII10"))      # 10y real yield
    dx = align(d["date"], fred("DTWEXBGS"))     # broad dollar index
    # 20-day macro change (rising/falling)
    ry_chg = ry - np.concatenate([np.full(20, np.nan), ry[:-20]])
    dx_chg = dx - np.concatenate([np.full(20, np.nan), dx[:-20]])
    yrs = (d["date"].iloc[-1]-d["date"].iloc[0]).days/365.25
    print(f"GOLD daily {yrs:.1f}yr | Turtle breakout N20/M10 | macro filter test | split-half\n")
    gates = {
        "baseline (no macro)": None,
        "LONG if yields falling / SHORT if rising": lambda dr, i: not np.isnan(ry_chg[i]) and (
            (dr == "buy" and ry_chg[i] < 0) or (dr == "sell" and ry_chg[i] > 0)),
        "LONG if dollar falling / SHORT if rising": lambda dr, i: not np.isnan(dx_chg[i]) and (
            (dr == "buy" and dx_chg[i] < 0) or (dr == "sell" and dx_chg[i] > 0)),
        "LONG if yields OR dollar falling": lambda dr, i: not (np.isnan(ry_chg[i]) or np.isnan(dx_chg[i])) and (
            (dr == "buy" and (ry_chg[i] < 0 or dx_chg[i] < 0)) or (dr == "sell" and (ry_chg[i] > 0 or dx_chg[i] > 0))),
        "LONG-only when yields falling (no shorts)": lambda dr, i: dr == "buy" and not np.isnan(ry_chg[i]) and ry_chg[i] < 0,
    }
    print(f"  {'variant':<48}{'trades':>7}{'win%':>6}{'final$':>9}{'P&L':>9}{'DD':>5}{'1st':>9}{'2nd':>9}{'rob':>5}")
    for nm, g in gates.items():
        r = backtest(d, g)
        if r is None: print(f"  {nm:<48} (no trades)"); continue
        bal, ntr, win, dd, b1, b2 = r
        rob = "YES" if (bal > START and b1 > START and b2 > START) else ""
        print(f"  {nm:<48}{ntr:>7}{win:>5.0f}%{bal:>9.0f}{bal-START:>+9.0f}{dd:>4.0f}%"
              f"{('$'+format(b1,'.0f')):>9}{('$'+format(b2,'.0f')):>9}{rob:>5}")


if __name__ == "__main__":
    main()
