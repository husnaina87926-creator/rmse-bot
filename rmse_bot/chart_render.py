"""Render a clean candlestick chart image (candles + EMAs) for the AI to 'look at'."""
import matplotlib
matplotlib.use("Agg")          # headless backend (works on free cloud, no display)

import pandas as pd
import mplfinance as mpf
from rmse_bot.indicators import ema


def render_chart(df: pd.DataFrame, path: str, lookback: int = 80, title: str = "") -> str:
    """Render the last `lookback` candles of a canonical OHLC frame to a PNG with
    EMA(9/21/50) overlays. EMAs are computed on the full series for accuracy, then
    sliced to the visible window. Returns the saved path."""
    full = df.copy()
    full.index = pd.to_datetime(full["time"])
    e9 = ema(full["close"], 9)
    e21 = ema(full["close"], 21)
    e50 = ema(full["close"], 50)

    sl = slice(-lookback, None)
    plot_df = full[["open", "high", "low", "close"]].iloc[sl].rename(columns=str.capitalize)
    apds = [
        mpf.make_addplot(e9.iloc[sl], color="#1f77b4", width=0.8),
        mpf.make_addplot(e21.iloc[sl], color="#ff7f0e", width=0.8),
        mpf.make_addplot(e50.iloc[sl], color="#9467bd", width=0.8),
    ]
    mpf.plot(plot_df, type="candle", addplot=apds, style="charles",
             title=title, ylabel="", volume=False,
             savefig=dict(fname=path, dpi=90, bbox_inches="tight"))
    return path
