import datetime as dt
import json
import os

from rmse_bot.llm_news import _parse_llm_json, run_news_sentinel, latest_sentiment
import rmse_bot.llm_news as ln


def test_parse_llm_json_variants():
    ok = _parse_llm_json('{"market": -2, "btc": -1, "top_risk": "ETF outflows"}')
    assert ok["market"] == -2 and ok["btc"] == -1
    fenced = _parse_llm_json('Here you go:\n```json\n{"market": 5}\n```')
    assert fenced["market"] == 2                    # clamped to [-2, 2]
    assert _parse_llm_json("no json here") is None
    assert _parse_llm_json('{"btc": 1}') is None    # market required
    assert _parse_llm_json('{"market": "very bad"}') is None


def test_sentinel_off_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert run_news_sentinel(str(tmp_path)) == {}
    assert not os.path.exists(os.path.join(str(tmp_path), "news_sentiment.json"))


def test_sentinel_journals_and_respects_ttl(tmp_path, monkeypatch):
    from rmse_bot.journal import read_events
    sd = str(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(ln, "fetch_headlines", lambda: ["BTC ETF approved", "Exchange hacked"])
    monkeypatch.setattr(ln, "llm_sentiment",
                        lambda h, k, **kw: {"market": -2, "btc": -2, "eth": None,
                                            "gold": None, "top_risk": "Exchange hacked"})
    now = dt.datetime(2026, 7, 2, 12, 0, tzinfo=dt.timezone.utc)
    s = run_news_sentinel(sd, now=now)
    assert s["market"] == -2 and s["n_headlines"] == 2
    evs = [e for e in read_events(sd) if e["type"] == "news_sentiment"]
    assert len(evs) == 1 and evs[0]["top_risk"] == "Exchange hacked"
    # 30 min later: TTL -> no second LLM call / journal entry
    monkeypatch.setattr(ln, "llm_sentiment", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    s2 = run_news_sentinel(sd, now=now + dt.timedelta(minutes=30))
    assert s2["market"] == -2
    assert len([e for e in read_events(sd) if e["type"] == "news_sentiment"]) == 1
    # trade tagging helper: fresh -> score, stale -> None
    assert latest_sentiment(sd, now=now + dt.timedelta(minutes=30)) == -2
    assert latest_sentiment(sd, now=now + dt.timedelta(hours=5)) is None


def test_taxonomy_counts_negative_sentiment_trades(tmp_path):
    from rmse_bot.journal import append_event, mistake_taxonomy
    sd = str(tmp_path)
    append_event(sd, {"type": "close", "account": "btc", "symbol": "BTCUSDT",
                      "direction": "sell", "outcome": "sl", "pnl": -30.0,
                      "close_time": "2026-07-01 12:00:00", "llm_sentiment": -2})
    append_event(sd, {"type": "close", "account": "btc", "symbol": "BTCUSDT",
                      "direction": "sell", "outcome": "tp", "pnl": 50.0,
                      "close_time": "2026-07-01 16:00:00", "llm_sentiment": 1})
    mo = mistake_taxonomy(sd)["months"]["2026-07"]
    assert mo["neg_sentiment_trades"] == 1 and mo["neg_sentiment_net"] == -30.0
