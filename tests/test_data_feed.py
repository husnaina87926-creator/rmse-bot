import pandas as pd
from rmse_bot.data_feed import load_csv, normalize_ohlc, resample_ohlc


def test_resample_15m_to_1h():
    # four 15-min bars -> one 1h bar; open=first, high=max, low=min, close=last
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01 00:00", periods=4, freq="15min"),
        "open": [1.0, 1.1, 1.2, 1.3],
        "high": [1.5, 1.4, 1.6, 1.35],
        "low": [0.9, 1.0, 1.1, 1.25],
        "close": [1.1, 1.2, 1.3, 1.32],
    })
    out = resample_ohlc(df, "1h")
    assert len(out) == 1
    assert out["open"].iloc[0] == 1.0
    assert out["high"].iloc[0] == 1.6
    assert out["low"].iloc[0] == 0.9
    assert out["close"].iloc[0] == 1.32


def test_normalize_lowercases_and_sorts():
    raw = pd.DataFrame({
        "Time": pd.to_datetime(["2024-01-02", "2024-01-01"]),
        "Open": [2.0, 1.0], "High": [3.0, 2.0],
        "Low": [1.0, 0.5], "Close": [2.5, 1.5],
    })
    out = normalize_ohlc(raw)
    assert list(out.columns) == ["time", "open", "high", "low", "close"]
    assert out["close"].iloc[0] == 1.5  # sorted ascending by time


def test_load_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("time,open,high,low,close\n2024-01-01,1,2,0.5,1.5\n")
    df = load_csv(str(p))
    assert df["high"].iloc[0] == 2.0
