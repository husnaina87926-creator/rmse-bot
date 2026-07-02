"""REAL-TIME WebSocket runner — reacts within milliseconds of each 4h crypto candle
close (true zero poll-delay). The strategy/logic is UNCHANGED (reuses paper_trader.step
+ rules_for + regime, exactly like run_bots.py); only the TRIGGER changes: instead of
polling every N seconds, it subscribes to Binance's kline WebSocket and fires the exact
moment a candle closes. Gold (not on Binance) runs on a 5-min timer. Paper mode, no keys.

Consistency note: entries AND candle-based exits fire at candle close using the closed
bar's intrabar high/low — identical to the backtest. (For LIVE real orders, stops would
be placed as OCO on the exchange for tick-level exits; that's the Phase-2 execution step.)
Run: python scripts/run_realtime.py
"""
import sys
import os
import json
import asyncio
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.data_feed import fetch_twelvedata, fetch_dukascopy
from rmse_bot.regime import regime_state
from rmse_bot.paper_trader import load_state, save_state, step, default_params
from rmse_bot.news_filter import fetch_calendar, is_news_blocked
from rmse_bot.self_improve import load_live_rules, rules_for

import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")

cfg = load_config(os.path.join(ROOT, "config.yaml"))
rf = cfg.get("regime_filter", {})
EP, RN = rf.get("ema_period", 100), rf.get("rise_n", 20)
START_BAL = cfg["account"]["size_usd"]
KEY = os.environ.get("TWELVE_DATA_KEY")
CRYPTO = cfg["crypto_rules"]["symbols"]


def crypto_params():
    cr, ex = cfg["crypto_rules"], cfg["crypto_rules"]["exit"]
    p = default_params(cfg)
    p.update(sl_atr=ex["sl_atr"], rr=ex["rr"], max_hold=ex["max_hold"],
             be_atr=ex.get("be_atr", 0.0), risk_pct=cr["risk_pct"], leverage=cr["leverage"])
    return p


CPARAMS = crypto_params()
GPARAMS = default_params(cfg)


def run_symbol(sym, kind, params):
    """Fetch recent data + run champion & challenger step for ONE symbol (at candle close)."""
    now = dt.datetime.now(dt.timezone.utc)
    live = load_live_rules(os.path.join(STATE, "live_rules.json"))
    cand_path = os.path.join(STATE, "candidates.json")
    candidates = json.load(open(cand_path)) if os.path.exists(cand_path) else {}
    try:
        if kind == "gold":
            name = "gold"
            trade = fetch_twelvedata(sym, "15m", KEY) if KEY else \
                fetch_dukascopy(sym, "15m", now - dt.timedelta(days=12), now)
            daily = fetch_twelvedata(sym, "1d", KEY, 250) if KEY else \
                fetch_dukascopy(sym, "1d", now - dt.timedelta(days=400), now)
        else:
            name = sym[:-4].lower()
            trade = fetch_binance_klines(sym, "4h", now - dt.timedelta(days=60), now)
            daily = fetch_binance_klines(sym, "1d", now - dt.timedelta(days=300), now)
    except Exception as e:
        print(f"  WARN {sym} fetch: {e}", flush=True)
        return
    # DATA INTEGRITY GUARD: never act on broken data
    from rmse_bot.journal import integrity_check, diff_and_journal, append_event
    interval_s = 900 if kind == "gold" else 14400
    ok, reason = integrity_check(trade, interval_s, allow_session_gaps=(kind == "gold"))
    if not ok:
        print(f"  WARN {sym} data integrity: {reason} — skipping", flush=True)
        append_event(STATE, {"type": "data_skip", "account": name if kind != "gold" else "gold",
                             "symbol": sym, "reason": reason})
        return
    reg = regime_state(daily, EP, RN)
    news_blocked = False
    if kind == "gold" and cfg.get("news_filter", {}).get("enabled"):
        try:
            nf = cfg["news_filter"]
            news_blocked = is_news_blocked(now, fetch_calendar(), nf.get("currencies", ["USD"]),
                                           nf.get("impacts", ["High"]), nf.get("window_min", 30))
        except Exception:
            pass
    champ_rules = rules_for(sym, cfg, live)
    data, rs = {sym: trade}, {sym: reg}
    bar_time = trade["time"].iloc[-1]
    cs = load_state(os.path.join(STATE, f"{name}.json"), START_BAL)
    before = (len(cs["open"]), len(cs["closed"]))
    b_open, b_n = [dict(p) for p in cs["open"]], len(cs["closed"])
    step(cs, data, cfg, {sym: champ_rules}, now, params=params,
         regime_state_by_symbol=rs, news_blocked=news_blocked)
    save_state(cs, os.path.join(STATE, f"{name}.json"))
    diff_and_journal(STATE, name, b_open, b_n, cs, bar_time, interval_s)
    cand = candidates.get(sym)
    if cand:
        chs = load_state(os.path.join(STATE, f"{name}_chal.json"), START_BAL)
        b_open, b_n = [dict(p) for p in chs["open"]], len(chs["closed"])
        step(chs, data, cfg, {sym: champ_rules + [cand["rule"]]}, now, params=params,
             regime_state_by_symbol=rs, news_blocked=news_blocked)
        save_state(chs, os.path.join(STATE, f"{name}_chal.json"))
        diff_and_journal(STATE, f"{name}_chal", b_open, b_n, chs, bar_time, interval_s)
    changed = (len(cs["open"]), len(cs["closed"])) != before
    flag = "  <== ACTION" if changed else ""
    print(f"[{now:%H:%M:%S}] {name:5} {sym:9} regime={reg or '-':4} bal=${cs['balance']:.2f} "
          f"open={len(cs['open'])} closed={len(cs['closed'])}{flag}", flush=True)


async def initial_pass():
    loop = asyncio.get_running_loop()
    print("[init] one full pass so state is current...", flush=True)
    for sym in CRYPTO:
        await loop.run_in_executor(None, run_symbol, sym, "crypto", CPARAMS)
    await loop.run_in_executor(None, run_symbol, "XAUUSD", "gold", GPARAMS)


async def gold_timer():
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(300)          # gold is 15m + not on Binance -> 5-min timer
        try:
            await loop.run_in_executor(None, run_symbol, "XAUUSD", "gold", GPARAMS)
        except Exception as e:
            print(f"  WARN gold: {e}", flush=True)


async def crypto_ws():
    loop = asyncio.get_running_loop()
    streams = "/".join(f"{s.lower()}@kline_4h" for s in CRYPTO)
    # public-data WS (mirrors data-api.binance.vision REST) — not geo-restricted like stream.binance.com
    url = f"wss://data-stream.binance.vision/stream?streams={streams}"
    while True:
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                print(f"[WS] connected — real-time streaming {len(CRYPTO)} coins (4h klines)", flush=True)
                async for raw in ws:
                    msg = json.loads(raw)
                    k = msg.get("data", {}).get("k", {})
                    if k.get("x"):        # candle CLOSED -> react now (ms after close)
                        sym = msg["data"]["s"]
                        loop.run_in_executor(None, run_symbol, sym, "crypto", CPARAMS)
        except Exception as e:
            print(f"[WS] disconnected ({e}); reconnecting in 5s", flush=True)
            await asyncio.sleep(5)


async def main():
    print("REAL-TIME runner — WebSocket candle-close triggers (zero poll-delay)", flush=True)
    await initial_pass()
    await asyncio.gather(crypto_ws(), gold_timer())


if __name__ == "__main__":
    asyncio.run(main())
