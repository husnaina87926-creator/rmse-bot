"""Economic-calendar news filter (free, no key).

High-impact news (NFP, CPI, FOMC) causes violent spikes that wreck technical setups.
The bot avoids OPENING new trades within a window around such events. (Exits are NOT
blocked — open trades still hit SL/TP normally.)

Free source: Forex Factory's weekly calendar JSON mirror (faireconomy.media).
"""
import json
import urllib.request
import datetime as dt

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def parse_calendar(data: list) -> list:
    """Normalize raw calendar entries to {time(UTC), currency, impact, title}."""
    out = []
    for e in data:
        raw = e.get("date")
        if not raw:
            continue
        try:
            ts = dt.datetime.fromisoformat(raw)
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        out.append({
            "time": ts.astimezone(dt.timezone.utc),
            "currency": e.get("country", ""),
            "impact": e.get("impact", ""),
            "title": e.get("title", ""),
        })
    return out


def fetch_calendar(url: str = CALENDAR_URL, timeout: int = 15) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (RMSE_BOT)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_calendar(json.loads(r.read().decode()))


def is_news_blocked(now, events: list, currencies=("USD",), impacts=("High",),
                    window_min: int = 30) -> bool:
    """True if a matching high-impact event is within +/- window_min of `now`."""
    cur, imp = set(currencies), set(impacts)
    for e in events:
        if e["currency"] in cur and e["impact"] in imp:
            if abs((e["time"] - now).total_seconds()) <= window_min * 60:
                return True
    return False
