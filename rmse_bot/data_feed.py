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
