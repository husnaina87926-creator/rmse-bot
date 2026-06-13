import pandas as pd
from rmse_bot.config import load_config
from rmse_bot.signal_engine import generate_signal, Signal


def _df(vals):
    return pd.DataFrame({
        "high": [float(v) + 0.5 for v in vals],
        "low": [float(v) - 0.5 for v in vals],
        "close": [float(v) for v in vals],
        "time": pd.date_range("2024-01-01", periods=len(vals), freq="15min"),
    })


def test_no_signal_when_trend_range():
    cfg = load_config("config.yaml")
    flat = _df([100.0] * 250)
    assert generate_signal(flat, flat, cfg) is None


def test_buy_signal_in_uptrend_pullback():
    cfg = load_config("config.yaml")
    base = [100 + i * 0.45 for i in range(220)]   # strong uptrend
    pull = [base[-1] - i * 0.8 for i in range(1, 16)]  # pullback (EMA9 dips under EMA21)
    rec = [pull[-1] + i * 0.9 for i in range(1, 10)]   # recovery -> EMA9 crosses back up
    df = _df(base + pull + rec)
    sig = generate_signal(df, df, cfg)
    assert sig is not None
    assert sig.direction == "buy"
    assert sig.sl < sig.entry < sig.tp
    assert 50 <= sig.confidence <= 100
