from dataclasses import dataclass
import pandas as pd
from rmse_bot.indicators import ema, rsi, atr
from rmse_bot.structure import classify_trend, detect_bos


@dataclass
class Signal:
    direction: str   # "buy" | "sell"
    entry: float
    sl: float
    tp: float
    confidence: float
    reason: str
    time: object = None


def _crossed_up(fast: pd.Series, slow: pd.Series) -> bool:
    return fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]


def _crossed_down(fast: pd.Series, slow: pd.Series) -> bool:
    return fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]


def generate_signal(df_1h: pd.DataFrame, df_15m: pd.DataFrame, cfg: dict):
    s = cfg["signal"]
    r = cfg["risk"]
    trend = classify_trend(df_1h, s["ema_trend"])
    if trend == "range":
        return None

    fast = ema(df_15m["close"], s["ema_fast"])
    slow = ema(df_15m["close"], s["ema_slow"])
    rsi_v = float(rsi(df_15m["close"], s["rsi_period"]).iloc[-1])
    a = float(atr(df_15m, r["atr_period"]).iloc[-1])
    entry = float(df_15m["close"].iloc[-1])
    bos = detect_bos(df_15m)
    t = df_15m["time"].iloc[-1] if "time" in df_15m.columns else None

    if trend == "up" and _crossed_up(fast, slow) and 50 <= rsi_v <= 70:
        sl = entry - r["sl_atr_mult"] * a
        tp = entry + r["reward_ratio"] * (entry - sl)
        conf = 50 + (20 if bos == "bullish" else 0) + (15 if rsi_v >= 55 else 0)
        return Signal("buy", entry, sl, tp, min(conf, 100),
                      f"uptrend+cross+rsi{rsi_v:.0f}+bos:{bos}", t)

    if trend == "down" and _crossed_down(fast, slow) and 30 <= rsi_v <= 50:
        sl = entry + r["sl_atr_mult"] * a
        tp = entry - r["reward_ratio"] * (sl - entry)
        conf = 50 + (20 if bos == "bearish" else 0) + (15 if rsi_v <= 45 else 0)
        return Signal("sell", entry, sl, tp, min(conf, 100),
                      f"downtrend+cross+rsi{rsi_v:.0f}+bos:{bos}", t)

    return None
