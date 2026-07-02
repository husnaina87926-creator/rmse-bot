"""Binance market-data connector (PUBLIC — no API key needed).

Public klines (candles) for backtest/research and recent data. Uses the public
data endpoint (data-api.binance.vision) which serves market data without auth.
Real crypto data is free, real-time, deep history, and 24/7 — solves the limits we
hit with forex feeds. Trading/keys come later (testnet first); this is data only.
"""
import json
import urllib.request
import urllib.parse

import pandas as pd

from rmse_bot.data_feed import normalize_ohlc

KLINES_URL = "https://data-api.binance.vision/api/v3/klines"


def _parse_klines(data: list) -> pd.DataFrame:
    """Binance kline rows -> canonical UTC-aware OHLC frame.
    Each row: [openTime, open, high, low, close, volume, closeTime, ...]."""
    rows = [{"time": pd.to_datetime(k[0], unit="ms", utc=True),
             "open": k[1], "high": k[2], "low": k[3], "close": k[4],
             "volume": k[5]} for k in data]
    return normalize_ohlc(pd.DataFrame(rows))


def fetch_binance_klines(symbol: str, interval: str, start, end, limit: int = 1000) -> pd.DataFrame:
    """Paginate the public klines endpoint between start/end datetimes (UTC)."""
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    cur, out = start_ms, []
    while cur < end_ms:
        params = urllib.parse.urlencode({"symbol": symbol, "interval": interval,
                                         "startTime": cur, "endTime": end_ms, "limit": limit})
        req = urllib.request.Request(f"{KLINES_URL}?{params}", headers={"User-Agent": "rmse-bot"})
        with urllib.request.urlopen(req, timeout=30) as r:
            chunk = json.loads(r.read().decode())
        if not chunk:
            break
        out += chunk
        cur = chunk[-1][0] + 1
        if len(chunk) < limit:
            break
    return _parse_klines(out)
