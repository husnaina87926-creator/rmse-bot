import pandas as pd

REQUIRED = ["time", "open", "high", "low", "close"]


def normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    df["time"] = pd.to_datetime(df["time"])
    df = df[REQUIRED].sort_values("time").reset_index(drop=True)
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    return df


def load_csv(path: str) -> pd.DataFrame:
    return normalize_ohlc(pd.read_csv(path))


def fetch_yfinance(symbol: str, interval: str, period: str) -> pd.DataFrame:
    import yfinance as yf
    raw = yf.download(symbol, interval=interval, period=period,
                      progress=False, auto_adjust=False)
    raw = raw.reset_index()
    raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
    raw = raw.rename(columns={"Date": "time", "Datetime": "time"})
    return normalize_ohlc(raw)


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate a canonical OHLC frame to a higher timeframe (e.g. '1h')."""
    d = df.set_index("time")
    out = (d.resample(rule)
            .agg({"open": "first", "high": "max", "low": "min", "close": "last"})
            .dropna()
            .reset_index())
    return out


# dukascopy free historical (no API key) — real spot XAUUSD / EURUSD
DUKAS_INSTRUMENTS = {
    "XAUUSD": "INSTRUMENT_FX_METALS_XAU_USD",
    "EURUSD": "INSTRUMENT_FX_MAJORS_EUR_USD",
}
DUKAS_INTERVALS = {"15m": "INTERVAL_MIN_15", "1h": "INTERVAL_HOUR_1"}


def fetch_dukascopy(symbol: str, interval: str, start, end, offer: str = "bid") -> pd.DataFrame:
    import dukascopy_python
    from dukascopy_python import instruments as I
    instr = getattr(I, DUKAS_INSTRUMENTS[symbol])
    iv = getattr(dukascopy_python, DUKAS_INTERVALS[interval])
    side = (dukascopy_python.OFFER_SIDE_BID if offer == "bid"
            else dukascopy_python.OFFER_SIDE_ASK)
    raw = dukascopy_python.fetch(instr, iv, side, start, end)
    raw = raw.reset_index().rename(columns={"timestamp": "time"})
    return normalize_ohlc(raw)
