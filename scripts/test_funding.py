"""Does adding FUNDING RATE to the all-weather strategy help? Test baseline vs several
funding-filter variants, with split-half robustness. Funding (Binance futures, public,
no key) aligned to 4h bars. 10% risk, 20x, ~0.2% round fees.
Idea: over-leveraged longs (high +funding) -> squeeze-down risk; crowded shorts
(very -funding) -> squeeze-up risk. So gate entries by funding extremes.
Run: python scripts/test_funding.py
"""
import sys, os, json, urllib.request, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.config import load_config
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.discovery import build_features
from rmse_bot.indicators import atr as atr_fn
from rmse_bot.regime import regime_mask

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
COST_FRAC, LEV, START, RISK = 0.001, 20, 5000.0, 10.0
cfg = load_config("config.yaml")
rf = cfg["regime_filter"]; EP, RN = rf["ema_period"], rf["rise_n"]
EX = cfg["crypto_rules"]["exit"]


def fetch_funding(symbol):
    base = "https://fapi.binance.com/fapi/v1/fundingRate"
    out = []; start = 1567000000000
    while True:
        url = f"{base}?symbol={symbol}&startTime={start}&limit=1000"
        req = urllib.request.Request(url, headers={"User-Agent": "x"})
        d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        if not d: break
        out += [(int(x["fundingTime"]), float(x["fundingRate"])) for x in d]
        if len(d) < 1000: break
        start = out[-1][0] + 1
    t = np.array([x[0] for x in out]); v = np.array([x[1] for x in out])
    return t, v


def funding_series(times_ns, ft, fv):
    """For each bar time, the most recent funding rate (forward-fill)."""
    tb = times_ns.astype("datetime64[ms]").astype("int64")  # -> ms regardless of source unit
    idx = np.searchsorted(ft, tb, side="right") - 1
    idx = np.clip(idx, 0, len(fv) - 1)
    out = np.where(idx >= 0, fv[idx], np.nan)
    out[tb < ft[0]] = np.nan
    return out


def allweather(df, daily, cost_unit, fund, gate=None):
    feats = build_features(df); a = atr_fn(df, cfg["risk"]["atr_period"]).values
    c = df["close"].values; times = df["time"].values; n = len(df)
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
    sl_atr, rr, hold = EX["sl_atr"], EX["rr"], EX["max_hold"]
    bal = START; tt = []; tp = []; i = 250; j = 0
    while i < n-1:
        while j+1 < len(dtimes) and dtimes[j+1] <= times[i]: j += 1
        cur = dregs[j] if dtimes[j] <= times[i] else None
        row = feats.iloc[i]; matched = None
        for d, reg, when in rules:
            if reg != cur: continue
            if all(bool(row[x]) for x in when): matched = d; break
        if matched is None or np.isnan(a[i]) or a[i] == 0: i += 1; continue
        d = matched
        if gate is not None and not gate(d, fund[i]):   # funding filter
            i += 1; continue
        entry = float(c[i])
        if d == "buy": sl, tp_ = entry-sl_atr*a[i], entry+rr*sl_atr*a[i]
        else: sl, tp_ = entry+sl_atr*a[i], entry-rr*sl_atr*a[i]
        rp = abs(entry-sl)
        if rp < entry*0.003:            # skip degenerate near-zero-vol stops (data artifact)
            i += 1; continue
        # FIXED risk on START (additive, no compounding blow-up) for a clean comparison
        units = min((START*RISK/100)/rp, (START*LEV)/entry)
        fut = df.iloc[i+1:i+1+hold]
        if fut.empty: break
        ep2, ci = float(fut["close"].iloc[-1]), min(i+hold, n-1)
        for k,(_,b) in enumerate(fut.iterrows()):
            if d == "buy":
                if b["low"] <= sl: ep2, ci = sl, i+1+k; break
                if b["high"] >= tp_: ep2, ci = tp_, i+1+k; break
            else:
                if b["high"] >= sl: ep2, ci = sl, i+1+k; break
                if b["low"] <= tp_: ep2, ci = tp_, i+1+k; break
        move = (ep2-entry) if d == "buy" else (entry-ep2)
        pnl = move*units - (entry+ep2)*units*cost_unit
        bal += pnl; tt.append(times[ci]); tp.append(pnl); i = i+hold
    return tt, tp


def summ(df, tt, tp):
    if not tp: return None
    bal = START; peak = START; mdd = 0
    for p in tp: bal += p; peak = max(peak, bal); mdd = max(mdd, (peak-bal)/peak)
    yrs = (df["time"].iloc[-1]-df["time"].iloc[0]).days/365.25
    cagr = ((bal/START)**(1/yrs)-1)*100 if bal > 0 else -100
    mid = df["time"].values[len(df)//2]
    b1 = START + sum(p for t, p in zip(tt, tp) if t < mid)
    b2 = START + sum(p for t, p in zip(tt, tp) if t >= mid)
    win = sum(1 for p in tp if p > 0)/len(tp)*100
    return bal, len(tp), win, cagr, mdd*100, b1, b2


def _retry(fn, *a, **k):
    import time
    for att in range(4):
        try:
            return fn(*a, **k)
        except Exception as e:
            if att == 3:
                raise
            time.sleep(4)


def main():
    now = dt.datetime.now(dt.timezone.utc)
    print("All-weather + FUNDING filter | 4h | FIXED 10% risk (additive) | split-half robustness\n")
    for sym in COINS:
        df = _retry(fetch_binance_klines, sym, "4h", now - dt.timedelta(days=2600), now)
        daily = _retry(fetch_binance_klines, sym, "1d", now - dt.timedelta(days=2600), now)
        ft, fv = fetch_funding(sym)
        fund = funding_series(df["time"].values, ft, fv)
        cu = COST_FRAC          # 0.001 = 0.1%/side -> ~0.2% round (FRACTION of notional)
        # funding percentiles for thresholds
        fok = fund[~np.isnan(fund)]
        p70, p30, p85, p15 = np.percentile(fok, [70, 30, 85, 15])
        print(f"=== {sym} === funding pctl: 15%={p15:.5f} 30%={p30:.5f} 70%={p70:.5f} 85%={p85:.5f}")
        # gates
        gates = {
            "baseline (no funding)": None,
            "skip LONG if fund>85p, SHORT if fund<15p": lambda d, f: not (np.isnan(f)) and (
                (d == "buy" and f <= p85) or (d == "sell" and f >= p15)),
            "SHORT only if fund>median, LONG if fund<median": lambda d, f: not np.isnan(f) and (
                (d == "sell" and f > 0) or (d == "buy" and f < 0)),
            "skip if funding NaN only (sanity vs baseline-on-perp)": lambda d, f: not np.isnan(f),
            "fade crowd: SHORT if fund>70p, LONG if fund<30p": lambda d, f: not np.isnan(f) and (
                (d == "sell" and f >= p70) or (d == "buy" and f <= p30)),
        }
        print(f"  {'variant':<52}{'trades':>7}{'win%':>6}{'CAGR':>8}{'DD':>5}{'1st':>9}{'2nd':>9}{'rob':>5}")
        for nm, gate in gates.items():
            tt, tp = allweather(df, daily, cu, fund, gate)
            s = summ(df, tt, tp)
            if s is None: print(f"  {nm:<52} (no trades)"); continue
            bal, ntr, win, cagr, dd, b1, b2 = s
            rob = "YES" if (bal > START and b1 > START and b2 > START) else ""
            print(f"  {nm:<52}{ntr:>7}{win:>5.0f}%{cagr:>+7.1f}%{dd:>4.0f}%"
                  f"{('$'+format(b1,'.0f')):>9}{('$'+format(b2,'.0f')):>9}{rob:>5}")
        print()


if __name__ == "__main__":
    main()
