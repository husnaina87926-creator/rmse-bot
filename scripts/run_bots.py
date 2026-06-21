"""Unified multi-bot runner: 3 independent paper accounts, each $5000.

  gold (XAUUSD) — TwelveData 15m, momentum LONG only in up-regime, USD news filter
  btc  (BTCUSDT) — Binance 4h, all-weather (short down-regime / long up-regime)
  eth  (ETHUSDT) — Binance 4h, all-weather

Each has its own state file, balance, fees, leverage, risk. Runs every ~15 min
(crypto 4h positions are just managed between 4h closes). No key needed for crypto.
Run from project root:  python scripts/run_bots.py
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import fetch_twelvedata, fetch_dukascopy
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.regime import regime_state
from rmse_bot.paper_trader import load_state, save_state, step, default_params
from rmse_bot.news_filter import fetch_calendar, is_news_blocked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def crypto_params(cfg):
    cr = cfg["crypto_rules"]; ex = cr["exit"]
    p = default_params(cfg)
    p.update(sl_atr=ex["sl_atr"], rr=ex["rr"], max_hold=ex["max_hold"],
             be_atr=ex.get("be_atr", 0.0), risk_pct=cr["risk_pct"], leverage=cr["leverage"])
    return p


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    now = dt.datetime.now(dt.timezone.utc)
    key = os.environ.get("TWELVE_DATA_KEY")
    start_bal = cfg["account"]["size_usd"]
    rf = cfg.get("regime_filter", {})
    ep, rn = rf.get("ema_period", 100), rf.get("rise_n", 20)

    accounts = [{"name": "gold", "symbol": "XAUUSD", "kind": "gold",
                 "rules": cfg["edge_rules"], "params": default_params(cfg)}]
    for sym in cfg["crypto_rules"]["symbols"]:
        accounts.append({"name": sym[:3].lower(), "symbol": sym, "kind": "crypto",
                         "rules": {sym: cfg["crypto_rules"]["rules"]}, "params": crypto_params(cfg)})

    print(f"[{now:%Y-%m-%d %H:%M} UTC] bots step")
    for acc in accounts:
        sym = acc["symbol"]
        try:
            if acc["kind"] == "gold":
                trade = fetch_twelvedata(sym, "15m", key) if key else \
                    fetch_dukascopy(sym, "15m", now - dt.timedelta(days=12), now)
                daily = fetch_twelvedata(sym, "1d", key, 250) if key else \
                    fetch_dukascopy(sym, "1d", now - dt.timedelta(days=400), now)
            else:
                trade = fetch_binance_klines(sym, "4h", now - dt.timedelta(days=60), now)
                daily = fetch_binance_klines(sym, "1d", now - dt.timedelta(days=300), now)
        except Exception as e:
            print(f"  WARN {acc['name']} fetch failed: {e}")
            continue

        reg = regime_state(daily, ep, rn)
        news_blocked = False
        if acc["kind"] == "gold" and cfg.get("news_filter", {}).get("enabled"):
            try:
                nf = cfg["news_filter"]
                news_blocked = is_news_blocked(now, fetch_calendar(), nf.get("currencies", ["USD"]),
                                               nf.get("impacts", ["High"]), nf.get("window_min", 30))
            except Exception as e:
                print(f"  WARN news: {e}")

        path = os.path.join(ROOT, "state", f"{acc['name']}.json")
        state = load_state(path, start_bal)
        step(state, {sym: trade}, cfg, acc["rules"], now, params=acc["params"],
             regime_state_by_symbol={sym: reg}, news_blocked=news_blocked)
        save_state(state, path)

        closed = state["closed"]
        wins = [t for t in closed if t["pnl"] > 0]
        wr = len(wins) / len(closed) if closed else 0
        print(f"  {acc['name']:5} {sym:8} regime={reg or '-':4} "
              f"balance=${state['balance']:.2f} open={len(state['open'])} "
              f"closed={len(closed)} win={wr:.0%}")


if __name__ == "__main__":
    main()
