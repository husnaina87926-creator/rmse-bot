from rmse_bot.binance_feed import _parse_klines


def test_parse_klines_to_ohlc():
    # [openTime(ms), open, high, low, close, volume, ...]
    data = [
        [1718000000000, "61000.0", "61200.0", "60900.0", "61150.0", "12.3", 1718000899999],
        [1718000900000, "61150.0", "61300.0", "61100.0", "61250.0", "8.1", 1718001799999],
    ]
    df = _parse_klines(data)
    assert list(df.columns) == ["time", "open", "high", "low", "close"]
    assert df["close"].iloc[0] == 61150.0
    assert df["high"].iloc[1] == 61300.0
    assert str(df["time"].dt.tz) == "UTC"
