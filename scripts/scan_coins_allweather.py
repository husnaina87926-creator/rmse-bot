"""Scan famous crypto coins for a ROBUST all-weather edge (same template as BTC/ETH/SOL:
down-regime -> short momentum, up-regime -> long momentum, 4h, regime filter).
Critically: report FULL-period AND split-half (1st/2nd) so we keep ONLY coins that are
positive in BOTH halves (robust), not regime-luck. 10% risk, 20x cap, ~0.2% round fees.
Run: python scripts/scan_coins_allweather.py
"""
import sys, os, datetime as dt
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.config import load_config
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.discovery import build_features
from rmse_bot.indicators import atr as atr_fn
from rmse_bot.regime import regime_mask

_DEFAULT = ["ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT",
            "TRXUSDT", "MATICUSDT", "ATOMUSDT", "BCHUSDT", "XLMUSDT", "ETCUSDT",
            "UNIUSDT", "NEARUSDT", "FILUSDT", "INJUSDT", "APTUSDT", "SUIUSDT"]
_arg = next((a for a in sys.argv[1:] if "," in a), None)
COINS = [c if c.endswith("USDT") else c + "USDT" for c in (_arg.split(",") if _arg else _DEFAULT)]
_days = next((int(a) for a in sys.argv[1:] if a.isdigit()), 2600)
COST_FRAC, LEV, START, RISK = 0.001, 20, 5000.0, 10.0   # 0.1%/side -> 0.2% round
cfg = load_config("config.yaml")
rf = cfg["regime_filter"]; EP, RN = rf["ema_period"], rf["rise_n"]
EX = cfg["crypto_rules"]["exit"]


def allweather(df, daily, cost_unit):
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
    bal = START; tr_t = []; tr_p = []; i = 250; j = 0
    while i < n-1:
        while j+1 < len(dtimes) and dtimes[j+1] <= times[i]: j += 1
        cur = dregs[j] if dtimes[j] <= times[i] else None
        row = feats.iloc[i]; matched = None
        for d, reg, when in rules:
            if reg != cur: continue
            if all(bool(row[x]) for x in when): matched = d; break
        if matched is None or np.isnan(a[i]) or a[i] == 0: i += 1; continue
        d = matched; entry = float(c[i])
        if d == "buy": sl, tp = entry-sl_atr*a[i], entry+rr*sl_atr*a[i]
        else: sl, tp = entry+sl_atr*a[i], entry-rr*sl_atr*a[i]
        rp = abs(entry-sl); units = min((bal*RISK/100)/rp, (bal*LEV)/entry)
        fut = df.iloc[i+1:i+1+hold]
        if fut.empty: break
        ep2, ci = float(fut["close"].iloc[-1]), min(i+hold, n-1)
        for k,(_,b) in enumerate(fut.iterrows()):
            if d == "buy":
                if b["low"] <= sl: ep2, ci = sl, i+1+k; break
                if b["high"] >= tp: ep2, ci = tp, i+1+k; break
            else:
                if b["high"] >= sl: ep2, ci = sl, i+1+k; break
                if b["low"] <= tp: ep2, ci = tp, i+1+k; break
        move = (ep2-entry) if d == "buy" else (entry-ep2)
        pnl = move*units - (entry+ep2)*units*cost_unit
        bal += pnl; tr_t.append(times[ci]); tr_p.append(pnl); i = i+hold
    return tr_t, tr_p


def stats(tr_p):
    if not tr_p: return None
    bal = START; peak = START; mdd = 0
    for p in tr_p:
        bal += p; peak = max(peak, bal); mdd = max(mdd, (peak-bal)/peak)
    win = sum(1 for p in tr_p if p > 0)/len(tr_p)*100
    return bal, len(tr_p), win, mdd*100


def main():
    now = dt.datetime.now(dt.timezone.utc)
    print("All-weather on famous coins | 4h | 10% risk | 20x | ~0.2% round | split-half robustness\n")
    print(f"{'coin':10}{'yr':>4}{'trades':>7}{'win%':>6}{'FULL$':>9}{'CAGR':>7}{'DD':>5}{'  1st-half':>11}{'2nd-half':>11}{'  robust?':>9}")
    robust = []
    for sym in COINS:
        try:
            df = fetch_binance_klines(sym, "4h", now - dt.timedelta(days=_days), now)
            daily = fetch_binance_klines(sym, "1d", now - dt.timedelta(days=_days), now)
        except Exception as e:
            print(f"{sym:10} fetch failed: {str(e)[:30]}"); continue
        if len(df) < 2000:
            print(f"{sym:10} too little data ({len(df)})"); continue
        med = float(df["close"].median()); cost_unit = COST_FRAC * med
        yrs = (df["time"].iloc[-1]-df["time"].iloc[0]).days/365.25
        tt, tp = allweather(df, daily, cost_unit)
        s = stats(tp)
        if s is None: print(f"{sym:10} no trades"); continue
        fb, ntr, win, dd = s
        cagr = ((fb/START)**(1/yrs)-1)*100 if fb > 0 else -100
        # split-half by trade index time
        mid_t = df["time"].values[len(df)//2]
        h1 = [p for t, p in zip(tt, tp) if t < mid_t]
        h2 = [p for t, p in zip(tt, tp) if t >= mid_t]
        b1 = START + sum(h1); b2 = START + sum(h2)
        ok = b1 > START and b2 > START and fb > START
        tag = "YES" if ok else ""
        if ok: robust.append((sym, cagr, dd, ntr/((df['time'].iloc[-1]-df['time'].iloc[0]).days)))
        print(f"{sym:10}{yrs:>4.1f}{ntr:>7}{win:>5.0f}%{fb:>9.0f}{cagr:>+6.1f}%{dd:>4.0f}%"
              f"{('$'+format(b1,'.0f')):>11}{('$'+format(b2,'.0f')):>11}{tag:>9}")
    print("\n" + "="*70)
    if robust:
        print(f"ROBUST coins (positive FULL + both halves) — candidates to add:")
        for sym, cagr, dd, tpd in sorted(robust, key=lambda x: x[1], reverse=True):
            print(f"  {sym:10} CAGR {cagr:+.1f}%  maxDD {dd:.0f}%  ~{tpd:.2f} trades/day")
    else:
        print("NO coin passed robustness (full + both halves positive).")


if __name__ == "__main__":
    main()
