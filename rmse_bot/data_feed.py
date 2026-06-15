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
    "XAGUSD": "INSTRUMENT_FX_METALS_XAG_USD",          # silver
    "SPX500": "INSTRUMENT_IDX_AMERICA_E_SANDP_500",     # S&P 500 index
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


# Twelve Data free API (fresher live feed, no Windows). Needs a free API key.
TD_SYMBOLS = {"XAUUSD": "XAU/USD", "EURUSD": "EUR/USD"}
TD_INTERVALS = {"15m": "15min", "1h": "1h"}


def _parse_twelvedata(data: dict) -> pd.DataFrame:
    """Turn a Twelve Data time_series JSON payload into a canonical UTC-aware OHLC frame."""
    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(f"Twelve Data error: {data.get('message', data)}")
    df = pd.DataFrame(data["values"]).rename(columns={"datetime": "time"})
    out = normalize_ohlc(df)
    if out["time"].dt.tz is None:                     # keep tz-aware UTC for safe comparisons
        out["time"] = out["time"].dt.tz_localize("UTC")
    return out


def fetch_twelvedata(symbol: str, interval: str, apikey: str,
                     outputsize: int = 400) -> pd.DataFrame:
    import json
    import urllib.request
    import urllib.parse
    params = urllib.parse.urlencode({
        "symbol": TD_SYMBOLS.get(symbol, symbol),
        "interval": TD_INTERVALS.get(interval, interval),
        "outputsize": outputsize,
        "timezone": "UTC",
        "apikey": apikey,
    })
    url = "https://api.twelvedata.com/time_series?" + params
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode())
    return _parse_twelvedata(data)
