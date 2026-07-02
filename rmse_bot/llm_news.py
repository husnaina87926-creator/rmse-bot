"""LLM news sentinel (OBSERVER ONLY — never touches trading).

The one job an LLM is genuinely the right tool for here: reading unstructured news
TEXT. Hourly: pull free crypto-news RSS headlines -> one cheap LLM call classifies
market sentiment (-2..+2) + per-asset notes + the top risk headline -> journaled as
'news_sentiment' events and written to state/news_sentiment.json (dashboard + trade
tagging). Months of tagged trades let the mistake/ledger miners answer "do trades
during extreme sentiment lose?" with data. Any rule born from that answer must still
pass the normal rigor + forward-trial gates — the LLM itself never signals.

Config via env (never in the repo): OPENAI_API_KEY (required to activate),
LLM_MODEL (default gpt-4o-mini), OPENAI_BASE_URL (default api.openai.com).
No key -> everything silently off; the bot behaves exactly as before.
"""
import json
import os
import re
import datetime as dt
import urllib.request
import xml.etree.ElementTree as ET

RSS_FEEDS = (
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
)
CHECK_EVERY_S = 3600          # one LLM call per hour max (~$0.01/day on gpt-4o-mini)
STATE_FILE = "news_sentiment.json"


def fetch_headlines(feeds=RSS_FEEDS, per_feed: int = 15, timeout: int = 12) -> list:
    """Latest headline titles from free RSS feeds. Fail-open: errors -> fewer/none."""
    out = []
    for url in feeds:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (RMSE_BOT)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                root = ET.fromstring(r.read())
            for item in root.iter("item"):
                t = item.findtext("title")
                if t:
                    out.append(t.strip())
                if len(out) % per_feed == 0 and len(out) >= per_feed:
                    break
        except Exception:
            continue
    return out[: per_feed * len(feeds)]


def _parse_llm_json(text: str):
    """Strict-ish JSON extraction: accept a bare object or one wrapped in prose/fences."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or "market" not in obj:
        return None
    try:
        obj["market"] = max(-2, min(2, int(obj["market"])))
    except (TypeError, ValueError):
        return None
    return obj


def llm_sentiment(headlines: list, api_key: str, model: str = None,
                  base_url: str = None, timeout: int = 30):
    """One chat call -> {"market": -2..2, "btc": .., "eth": .., "gold": ..,
    "top_risk": "..."} or None. Uses plain urllib (no SDK dependency)."""
    if not headlines:
        return None
    model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
    base = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
    prompt = (
        "You are a markets analyst. Given these fresh crypto/finance news headlines, "
        "return ONLY a JSON object: {\"market\": int -2..2 (overall crypto sentiment; "
        "-2 very bearish, 0 neutral, 2 very bullish), \"btc\": int -2..2 or null, "
        "\"eth\": int -2..2 or null, \"gold\": int -2..2 or null, "
        "\"top_risk\": one short sentence naming the single most market-moving item, "
        "or null}. Judge only from the headlines; do not invent facts.\n\nHEADLINES:\n"
        + "\n".join(f"- {h}" for h in headlines[:40])
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 200,
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(r.read().decode())
        return _parse_llm_json(resp["choices"][0]["message"]["content"])
    except Exception:
        return None


def run_news_sentinel(state_dir: str, now=None) -> dict:
    """Hourly observer tick: headlines -> LLM sentiment -> journal + state file.
    Returns the latest sentiment dict (or {} when off/too-soon/failed)."""
    from rmse_bot.journal import append_event
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return {}                                  # feature off — bot unchanged
    now = now or dt.datetime.now(dt.timezone.utc)
    path = os.path.join(state_dir, STATE_FILE)
    if os.path.exists(path):
        try:
            with open(path) as f:
                prev = json.load(f)
            age = (now - dt.datetime.fromisoformat(prev["_ts"])).total_seconds()
            if age < CHECK_EVERY_S:
                return prev                        # fresh enough — no new call
        except Exception:
            pass
    heads = fetch_headlines()
    senti = llm_sentiment(heads, key)
    if senti is None:
        return {}
    senti["n_headlines"] = len(heads)
    senti["_ts"] = now.isoformat()
    with open(path, "w") as f:
        json.dump(senti, f, indent=2)
    append_event(state_dir, {"type": "news_sentiment", "market": senti.get("market"),
                             "btc": senti.get("btc"), "eth": senti.get("eth"),
                             "gold": senti.get("gold"), "top_risk": senti.get("top_risk"),
                             "n_headlines": len(heads)})
    return senti


def latest_sentiment(state_dir: str, max_age_s: int = 7200, now=None):
    """Most recent market-sentiment score if fresh, else None (for trade tagging)."""
    path = os.path.join(state_dir, STATE_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            s = json.load(f)
        now = now or dt.datetime.now(dt.timezone.utc)
        if (now - dt.datetime.fromisoformat(s["_ts"])).total_seconds() <= max_age_s:
            return s.get("market")
    except Exception:
        pass
    return None
