"""Higher-timeframe regime filter.

Our momentum edge is regime-dependent: over 10 years it was breakeven (PF 1.01) and
lost in bear markets, because brief bear-market rallies trip the on-timeframe trend
filter. Confirming the DAILY trend first (only trade when the daily trend is up) turned
the 10yr result from +$7 to +$110 and cut the 2012-15 bear loss from -$49 to -$6 —
robust across EMA50/100/150/200. So: only take longs when the daily regime is UP.
"""
import pandas as pd

from rmse_bot.data_feed import resample_ohlc
from rmse_bot.indicators import ema


def _daily_up(daily_close: pd.Series, ema_period: int, rise_n: int) -> pd.Series:
    e = ema(daily_close, ema_period)
    return (daily_close > e) & (e > e.shift(rise_n))


def regime_mask(df: pd.DataFrame, ema_period: int = 100, rise_n: int = 20):
    """Boolean array aligned to df rows: True where the DAILY regime is up.
    Used by the backtest so live == backtest."""
    daily = resample_ohlc(df, "1D")
    up = _daily_up(daily["close"], ema_period, rise_n)
    up.index = pd.to_datetime(daily["time"]).dt.date
    dates = pd.to_datetime(df["time"]).dt.date
    return dates.map(up).fillna(False).to_numpy(dtype=bool)


def regime_up_now(daily_df: pd.DataFrame, ema_period: int = 100, rise_n: int = 20) -> bool:
    """Is the daily regime up on the latest daily bar? Used live (from a daily fetch)."""
    if daily_df is None or len(daily_df) < ema_period:
        return False
    return bool(_daily_up(daily_df["close"], ema_period, rise_n).iloc[-1])
