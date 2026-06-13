import pandas as pd
from rmse_bot.data_feed import load_csv, normalize_ohlc


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
