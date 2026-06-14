import os
import pandas as pd
from rmse_bot.chart_render import render_chart


def test_render_chart_creates_png(tmp_path):
    n = 120
    close = [1000 + (i % 10) for i in range(n)]
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
        "open": close,
        "high": [c + 2 for c in close],
        "low": [c - 2 for c in close],
        "close": close,
    })
    out = tmp_path / "chart.png"
    render_chart(df, str(out), lookback=80, title="TEST")
    assert os.path.exists(out)
    assert os.path.getsize(out) > 1000   # a real image, not empty
