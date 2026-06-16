import pandas as pd
from rmse_bot.regime import regime_mask, regime_up_now


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
        "open": closes, "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes], "close": closes,
    })


def test_regime_up_when_rising():
    df = _df([100 + i * 0.1 for i in range(4000)])    # steady uptrend over many days
    mask = regime_mask(df, ema_period=20, rise_n=5)
    assert mask[-1] == True                            # latest bar: daily regime up


def test_regime_down_when_falling():
    df = _df([1000 - i * 0.1 for i in range(4000)])    # downtrend
    mask = regime_mask(df, ema_period=20, rise_n=5)
    assert mask[-1] == False


def test_regime_up_now_handles_short_data():
    daily = pd.DataFrame({"close": [1, 2, 3]})
    assert regime_up_now(daily, ema_period=100) is False   # not enough data -> False
