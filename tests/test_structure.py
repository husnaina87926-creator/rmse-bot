import pandas as pd
from rmse_bot.structure import find_swings, classify_trend, detect_bos


def test_find_swings_marks_local_extremes():
    # index 2 is a clear swing high (14), index 5 a swing low (8)
    df = pd.DataFrame({
        "high":  [10, 12, 14, 12, 10, 9,  11, 13],
        "low":   [9,  11, 13, 11, 9,  8,  10, 12],
        "close": [9.5, 11.5, 13.5, 11.5, 9.5, 8.5, 10.5, 12.5],
    }, dtype=float)
    out = find_swings(df, left=2, right=2)
    assert bool(out["swing_high"].iloc[2]) is True
    assert bool(out["swing_low"].iloc[5]) is True
    assert bool(out["swing_high"].iloc[0]) is False  # edges can't be swings


def _ramp(start, step, n):
    vals = [start + step * i for i in range(n)]
    return pd.DataFrame({"high": [v + 0.5 for v in vals],
                         "low": [v - 0.5 for v in vals],
                         "close": vals}, dtype=float)


def test_uptrend_when_price_above_rising_ema():
    df = _ramp(100, 1, 250)      # steadily rising
    assert classify_trend(df, ema_period=200) == "up"


def test_downtrend_when_price_below_falling_ema():
    df = _ramp(300, -1, 250)     # steadily falling
    assert classify_trend(df, ema_period=200) == "down"


def test_bullish_bos_when_close_breaks_last_swing_high():
    df = pd.DataFrame({
        "high":  [10, 12, 14, 12, 11, 13, 15.5],
        "low":   [9,  11, 13, 11, 10, 12, 14],
        "close": [9.5, 11.5, 13.5, 11.5, 10.5, 12.5, 15.2],  # last close 15.2 > swing high 14
    }, dtype=float)
    assert detect_bos(df) == "bullish"


def test_no_bos_when_range_bound():
    df = pd.DataFrame({
        "high":  [10, 12, 14, 12, 11, 13, 13.5],
        "low":   [9,  11, 13, 11, 10, 12, 12.5],
        "close": [9.5, 11.5, 13.5, 11.5, 10.5, 12.5, 13.0],
    }, dtype=float)
    assert detect_bos(df) == "none"
