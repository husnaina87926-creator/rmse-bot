"""Strengthen DOGE beyond the plain all-weather (+7.8%). Test variants — long-bias,
exit tuning, DOGE's OWN discovered entries — each with SPLIT-HALF robustness, and keep
only the strongest config that is positive in BOTH halves. 10% risk, 20x, ~0.2% round.
Run: python scripts/strengthen_doge.py
"""
import sys, os, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.config import load_config
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.discovery import build_features
from rmse_bot.indicators import atr as atr_fn
from rmse_bot.strategy_generator import generate_strategies

SYM = "DOGEUSDT"
cfg = load_config("config.yaml")
rf = cfg["regime_filter"]; EP, RN = rf["ema_period"], rf["rise_n"]
COST_FRAC, LEV, START, RISK = 0.001, 20, 5000.0, 10.0


def regimes(daily):
    dclose = daily["close"].values; ema = pd.Series(dclose).ewm(span=EP, adjust=False).mean().values
    out = []
    for k in range(len(daily)):
        if k < EP: out.append(None); continue
        rising = ema[k] > ema[k-RN] if k >= RN else False
        if dclose[k] > ema[k] and rising: out.append("up")
        elif dclose[k] < ema[k] and not rising: out.append("down")
        else: out.append(None)
    return out, daily["time"].values


def run(df, dregs, dtimes, rules, ex, cost_unit):
    feats = build_features(df); a = atr_fn(df, cfg["risk"]["atr_period"]).values
    c = df["close"].values; times = df["time"].values; n = len(df)
    sl_atr, rr, hold, be = ex["sl_atr"], ex["rr"], ex["max_hold"], ex.get("be_atr", 0.0)
    bal = START; tt = []; tp = []; i = 250; j = 0
    while i < n-1:
        while j+1 < len(dtimes) and dtimes[j+1] <= times[i]: j += 1
        cur = dregs[j] if dtimes[j] <= times[i] else None
        row = feats.iloc[i]; matched = None
        for d, reg, when in rules:
            if reg and reg != cur: continue
            if all(bool(row[x]) for x in when): matched = d; break
        if matched is None or np.isnan(a[i]) or a[i] == 0: i += 1; continue
        d = matched; entry = float(c[i])
        if d == "buy": sl, tp_ = entry-sl_atr*a[i], entry+rr*sl_atr*a[i]
        else: sl, tp_ = entry+sl_atr*a[i], entry-rr*sl_atr*a[i]
        rp = abs(entry-sl); units = min((bal*RISK/100)/rp, (bal*LEV)/entry)
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


def summarize(df, tt, tp):
    if not tp: return None
    bal = START; peak = START; mdd = 0
    for p in tp:
        bal += p; peak = max(peak, bal); mdd = max(mdd, (peak-bal)/peak)
    yrs = (df["time"].iloc[-1]-df["time"].iloc[0]).days/365.25
    cagr = ((bal/START)**(1/yrs)-1)*100 if bal > 0 else -100
    mid = df["time"].values[len(df)//2]
    b1 = START + sum(p for t, p in zip(tt, tp) if t < mid)
    b2 = START + sum(p for t, p in zip(tt, tp) if t >= mid)
    win = sum(1 for p in tp if p > 0)/len(tp)*100
    return bal, len(tp), win, cagr, mdd*100, b1, b2


def main():
    now = dt.datetime.now(dt.timezone.utc)
    df = fetch_binance_klines(SYM, "4h", now - dt.timedelta(days=2600), now)
    daily = fetch_binance_klines(SYM, "1d", now - dt.timedelta(days=2600), now)
    dregs, dtimes = regimes(daily)
    med = float(df["close"].median()); cu = COST_FRAC*med
    AW = [("sell","down",["rsi_bear","high_vol","strong_trend"]),
          ("buy","up",["rsi_overbought","high_vol","strong_trend"])]
    LONG = [("buy","up",["rsi_overbought","high_vol","strong_trend"])]
    e10 = {"sl_atr":2.0,"rr":1.0,"max_hold":24,"be_atr":0.0}
    variants = [
        ("AW standard (baseline)", AW, e10),
        ("AW long-only", LONG, e10),
        ("AW rr1.5", AW, {**e10,"rr":1.5}),
        ("AW rr0.75", AW, {**e10,"rr":0.75}),
        ("AW long-only rr1.5", LONG, {**e10,"rr":1.5}),
        ("AW be1.0", AW, {**e10,"be_atr":1.0}),
    ]
    # DOGE's own discovered top entries (cross with regime up=buy/down=sell)
    cfg["instruments"][SYM] = {"contract_size":1,"spread_price":cu,"slippage_price":cu,
                               "commission_per_lot":0.0,"swap_per_lot":0.0}
    board = generate_strategies(df, cfg, SYM, max_entries=10, min_count=120)
    seen = set()
    for s in sorted(board, key=lambda x: x["return"], reverse=True)[:6]:
        key = tuple(sorted(s["entry"]))
        if key in seen: continue
        seen.add(key)
        reg = "up" if s["direction"] == "buy" else "down"
        variants.append((f"OWN {s['direction']} {' & '.join(s['entry'])[:24]}",
                         [(s["direction"], reg, s["entry"])], e10))

    print(f"DOGE strengthening | 4h | 10% risk | split-half robustness\n")
    print(f"{'variant':<40}{'trades':>7}{'win%':>6}{'CAGR':>8}{'DD':>5}{'1st':>9}{'2nd':>9}{'robust':>8}")
    best = None
    for nm, rules, ex in variants:
        tt, tp = run(df, dregs, dtimes, rules, ex, cu)
        s = summarize(df, tt, tp)
        if s is None: print(f"{nm:<40}  (no trades)"); continue
        bal, ntr, win, cagr, dd, b1, b2 = s
        robust = bal > START and b1 > START and b2 > START
        tag = "YES" if robust else ""
        print(f"{nm:<40}{ntr:>7}{win:>5.0f}%{cagr:>+7.1f}%{dd:>4.0f}%{('$'+format(b1,'.0f')):>9}{('$'+format(b2,'.0f')):>9}{tag:>8}")
        if robust and (best is None or cagr > best[1]):
            best = (nm, cagr, rules, ex)
    print("\n" + "="*60)
    if best:
        print(f"STRONGEST ROBUST DOGE variant: {best[0]}  (CAGR {best[1]:+.1f}%)")
        print(f"  rules: {best[2]}")
        print(f"  exit:  {best[3]}")
    else:
        print("No robust variant beat baseline.")


if __name__ == "__main__":
    main()
