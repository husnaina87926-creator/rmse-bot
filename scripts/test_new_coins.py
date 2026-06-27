"""Backtest the live all-weather crypto strategy on candidate coins (BNB/SOL/XRP)
over their FULL Binance history, with realistic round-trip costs, before deciding
whether to add any to the bot. Mirrors paper_trader: per-rule regime filter
(sell only in down-regime, buy only in up-regime), ATR SL/TP, 10% risk, 20x lev.
Run from project root:  python scripts/test_new_coins.py
"""
import sys, os, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.discovery import build_features
from rmse_bot.indicators import atr
from rmse_bot.regime import regime_state
import pandas as pd

COINS = ["BNBUSDT", "SOLUSDT", "XRPUSDT", "BTCUSDT", "ETHUSDT"]  # last two = reference
ROUND_TRIP_COST = 0.0025   # 0.25% of notional per trade (Binance fees + realistic slippage)


def daily_regime_series(daily, ep, rn):
    """regime label ('up'/'down'/None) as of each daily close, forward-filled to 4h bars."""
    out = {}
    closes = daily["close"].values
    times = daily["time"].values
    ema = pd.Series(closes).ewm(span=ep, adjust=False).mean().values
    for i in range(len(daily)):
        if i < ep:
            out[times[i]] = None
            continue
        rising = ema[i] > ema[i - rn] if i >= rn else False
        if closes[i] > ema[i] and rising:
            out[times[i]] = "up"
        elif closes[i] < ema[i] and not rising:
            out[times[i]] = "down"
        else:
            out[times[i]] = None
    return daily.assign(reg=[out[t] for t in times])[["time", "reg"]]


def backtest_allweather(df, daily, cfg, rules, ep, rn):
    feats = build_features(df)
    a = atr(df, cfg["risk"]["atr_period"]).values
    close = df["close"].values
    times = df["time"].values
    # map each 4h bar to most recent daily regime
    dreg = daily_regime_series(daily, ep, rn)
    dreg = dreg.dropna(subset=["reg"])
    reg_times = dreg["time"].values
    reg_vals = dreg["reg"].values
    bal = cfg["account"]["size_usd"]
    risk_pct = cfg["crypto_rules"]["risk_pct"]
    ex = cfg["crypto_rules"]["exit"]
    sl_atr, rr, max_hold = ex["sl_atr"], ex["rr"], ex["max_hold"]
    trades, wins = [], 0
    n = len(df)
    i = 250
    j = 0
    while i < n - 1:
        # advance regime pointer to last daily <= current bar time
        while j + 1 < len(reg_times) and reg_times[j + 1] <= times[i]:
            j += 1
        cur_reg = reg_vals[j] if len(reg_vals) and reg_times[j] <= times[i] else None
        row = feats.iloc[i]
        matched = None
        for rule in rules:
            if rule.get("regime") and rule["regime"] != cur_reg:
                continue
            if all(bool(row[c]) for c in rule["when"]):
                matched = rule
                break
        if matched is None or np.isnan(a[i]) or a[i] == 0:
            i += 1
            continue
        entry = float(close[i])
        d = matched["direction"]
        if d == "buy":
            sl, tp = entry - sl_atr * a[i], entry + rr * sl_atr * a[i]
        else:
            sl, tp = entry + sl_atr * a[i], entry - rr * sl_atr * a[i]
        # risk-based size: lose risk_pct of balance if SL hits
        risk_amt = bal * risk_pct / 100.0
        stop_dist = abs(entry - sl)
        units = risk_amt / stop_dist
        notional = units * entry
        future = df.iloc[i + 1:i + 1 + max_hold]
        if future.empty:
            break
        outcome, exit_price = "time", float(future["close"].iloc[-1])
        for _, b in future.iterrows():
            if d == "buy":
                if b["low"] <= sl: outcome, exit_price = "sl", sl; break
                if b["high"] >= tp: outcome, exit_price = "tp", tp; break
            else:
                if b["high"] >= sl: outcome, exit_price = "sl", sl; break
                if b["low"] <= tp: outcome, exit_price = "tp", tp; break
        move = (exit_price - entry) if d == "buy" else (entry - exit_price)
        pnl = move * units - notional * ROUND_TRIP_COST
        bal += pnl
        if pnl > 0: wins += 1
        trades.append(pnl)
        i += max_hold
    return bal, trades, wins


def main():
    cfg = load_config("config.yaml")
    now = dt.datetime.now(dt.timezone.utc)
    rf = cfg["regime_filter"]; ep, rn = rf["ema_period"], rf["rise_n"]
    rules = cfg["crypto_rules"]["rules"]
    start = cfg["account"]["size_usd"]
    print(f"All-weather strategy | start ${start:.0f} | 10% risk | cost {ROUND_TRIP_COST*100:.2f}%/trade")
    print(f"{'coin':9}{'years':>6}{'trades':>8}{'win%':>7}{'final$':>12}{'totalP&L':>12}{'CAGR':>8}")
    for sym in COINS:
        try:
            df = fetch_binance_klines(sym, "4h", now - dt.timedelta(days=3650), now)
            daily = fetch_binance_klines(sym, "1d", now - dt.timedelta(days=3650), now)
        except Exception as e:
            print(f"{sym:9} fetch failed: {e}"); continue
        if len(df) < 500:
            print(f"{sym:9} too little data ({len(df)} bars)"); continue
        bal, trades, wins = backtest_allweather(df, daily, cfg, rules, ep, rn)
        yrs = (df["time"].iloc[-1] - df["time"].iloc[0]).days / 365.25
        wr = wins / len(trades) * 100 if trades else 0
        cagr = ((bal / start) ** (1 / yrs) - 1) * 100 if yrs > 0 and bal > 0 else -100
        tag = "  <-ref" if sym in ("BTCUSDT", "ETHUSDT") else ""
        print(f"{sym:9}{yrs:>6.1f}{len(trades):>8}{wr:>6.0f}%{bal:>12.0f}{bal-start:>+12.0f}{cagr:>+7.1f}%{tag}")


if __name__ == "__main__":
    main()
