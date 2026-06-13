import pandas as pd
from rmse_bot.indicators import ema


def find_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    out = df.copy()
    n = len(df)
    sh = [False] * n
    sl = [False] * n
    for i in range(left, n - right):
        window_h = df["high"].iloc[i - left:i + right + 1]
        window_l = df["low"].iloc[i - left:i + right + 1]
        if df["high"].iloc[i] == window_h.max() and (window_h == df["high"].iloc[i]).sum() == 1:
            sh[i] = True
        if df["low"].iloc[i] == window_l.min() and (window_l == df["low"].iloc[i]).sum() == 1:
            sl[i] = True
    out["swing_high"] = sh
    out["swing_low"] = sl
    return out


def classify_trend(df: pd.DataFrame, ema_period: int = 200) -> str:
    e = ema(df["close"], ema_period)
    price = df["close"].iloc[-1]
    slope = e.iloc[-1] - e.iloc[max(0, len(e) - 10)]
    if price > e.iloc[-1] and slope > 0:
        return "up"
    if price < e.iloc[-1] and slope < 0:
        return "down"
    return "range"


def detect_bos(df: pd.DataFrame) -> str:
    sw = find_swings(df, left=2, right=2)
    last_close = df["close"].iloc[-1]
    highs = sw.loc[sw["swing_high"], "high"]
    lows = sw.loc[sw["swing_low"], "low"]
    if not highs.empty and last_close > highs.iloc[-1]:
        return "bullish"
    if not lows.empty and last_close < lows.iloc[-1]:
        return "bearish"
    return "none"
