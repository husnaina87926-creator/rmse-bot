import pandas as pd
from rmse_bot.indicators import ema, rsi, atr


def test_ema_first_value_equals_first_price():
    s = pd.Series([10, 11, 12, 13, 14], dtype=float)
    out = ema(s, period=3)
    assert round(out.iloc[0], 6) == 10.0          # seeded with first value


def test_ema_known_value():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = ema(s, period=2)
    # alpha = 2/(2+1)=0.6667; ema2 = 1; then 0.6667*2+0.3333*1=1.6667
    assert round(out.iloc[1], 4) == 1.6667


def test_rsi_all_gains_is_100():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], dtype=float)
    out = rsi(s, period=14)
    assert round(out.iloc[-1], 1) == 100.0


def test_rsi_in_bounds():
    s = pd.Series([5, 4, 6, 3, 7, 2, 8, 1, 9, 5, 6, 4, 7, 3, 8, 6], dtype=float)
    out = rsi(s, period=14)
    assert 0 <= out.iloc[-1] <= 100


def test_atr_constant_range():
    # every candle has high-low = 2, no gaps -> ATR should converge to 2
    df = pd.DataFrame({
        "high":  [12, 13, 14, 15, 16],
        "low":   [10, 11, 12, 13, 14],
        "close": [11, 12, 13, 14, 15],
    }, dtype=float)
    out = atr(df, period=3)
    assert round(out.iloc[-1], 4) == 2.0
