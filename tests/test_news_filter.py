import datetime as dt
from rmse_bot.news_filter import parse_calendar, is_news_blocked


def test_parse_calendar_normalizes():
    data = [{"title": "CPI", "country": "USD", "date": "2026-06-17T12:30:00+00:00", "impact": "High"},
            {"title": "x", "country": "EUR", "date": None, "impact": "Low"}]   # bad date -> dropped
    out = parse_calendar(data)
    assert len(out) == 1
    assert out[0]["currency"] == "USD"
    assert str(out[0]["time"].tzinfo) == "UTC"


def test_is_news_blocked_within_window():
    now = dt.datetime(2026, 6, 17, 12, 25, tzinfo=dt.timezone.utc)
    events = [{"time": dt.datetime(2026, 6, 17, 12, 30, tzinfo=dt.timezone.utc),
               "currency": "USD", "impact": "High", "title": "CPI"}]
    assert is_news_blocked(now, events, window_min=30) is True       # 5 min before -> blocked


def test_is_news_blocked_outside_window():
    now = dt.datetime(2026, 6, 17, 10, 0, tzinfo=dt.timezone.utc)
    events = [{"time": dt.datetime(2026, 6, 17, 12, 30, tzinfo=dt.timezone.utc),
               "currency": "USD", "impact": "High", "title": "CPI"}]
    assert is_news_blocked(now, events, window_min=30) is False      # 2.5h away -> ok


def test_is_news_blocked_ignores_low_impact_and_other_currency():
    now = dt.datetime(2026, 6, 17, 12, 30, tzinfo=dt.timezone.utc)
    events = [{"time": now, "currency": "EUR", "impact": "High", "title": "x"},
              {"time": now, "currency": "USD", "impact": "Low", "title": "y"}]
    assert is_news_blocked(now, events) is False
