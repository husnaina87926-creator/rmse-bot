"""ALWAYS-ON LIVE BRAIN — event-driven self-improvement (runs 24/7 as a service).

Information arrives only when a candle CLOSES, so the brain is wired to events, not a
weekly cron:
  - every ~5 min : PROMOTION + DEMOTION pass (cheap — promotes forward-proven candidates
                   the moment they qualify; demotes decayed promotions the moment their
                   forward record since promotion goes negative over 20+ trades)
  - every 4h close: full DISCOVERY pass (crypto 4h data has new information exactly then;
                    gold refreshed on the same beat). Candidate STICKINESS keeps each
                    challenger running until it has had a fair 30-trade forward trial —
                    so frequent re-discovery never resets challengers prematurely.
This is the maximum useful learning frequency for a 4h system: anything faster would
re-read identical data and learn nothing. Run: python scripts/run_brain_live.py
"""
import sys
import os
import time
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.data_feed import fetch_dukascopy
from rmse_bot.self_improve import promotion_demotion_pass, discovery_pass
from rmse_bot.journal import health_snapshot, run_postmortems

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
NAME = {"XAUUSD": "gold", "BTCUSDT": "btc", "ETHUSDT": "eth", "SOLUSDT": "sol",
        "ADAUSDT": "ada", "DOGEUSDT": "doge", "OPUSDT": "op", "SEIUSDT": "sei",
        "VETUSDT": "vet", "GALAUSDT": "gala", "XTZUSDT": "xtz", "SANDUSDT": "sand",
        "MANAUSDT": "mana", "HBARUSDT": "hbar"}
CHECK_EVERY = 300          # seconds between promotion/demotion heartbeats


def fetch_for(sym):
    now = dt.datetime.now(dt.timezone.utc)
    if sym == "XAUUSD":
        return fetch_dukascopy(sym, "15m", now - dt.timedelta(days=500), now)
    return fetch_binance_klines(sym, "4h", now - dt.timedelta(days=1000), now)


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    start_bal = cfg["account"]["size_usd"]
    symbols = ["XAUUSD"] + list(cfg["crypto_rules"]["symbols"])
    last_4h = None
    last_pm = None
    acct_names = [NAME[s] for s in symbols] + [f"{NAME[s]}_chal" for s in symbols]
    print("[brain] ALWAYS-ON live brain started (5-min heartbeat, discovery at every 4h close)",
          flush=True)
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            promoted, demoted = promotion_demotion_pass(cfg, STATE, NAME, start_bal)
            for sym, rule in promoted:
                print(f"[brain {now:%m-%d %H:%M}] PROMOTED {sym}: {rule}", flush=True)
            for sym, rule in demoted:
                print(f"[brain {now:%m-%d %H:%M}] DEMOTED  {sym}: {rule} (forward decay)",
                      flush=True)
        except Exception as e:
            print(f"[brain] WARN promo/demo pass: {e}", flush=True)

        try:
            health = health_snapshot(STATE, acct_names, start_bal)
            for nm, h in health.items():
                if isinstance(h, dict) and h.get("unhealthy"):
                    print(f"[brain {now:%m-%d %H:%M}] HEALTH FLAG: {nm} last-20 net "
                          f"{h['recent_net']} (win {h['recent_win']})", flush=True)
        except Exception as e:
            print(f"[brain] WARN health: {e}", flush=True)

        if last_pm is None or (now - last_pm).total_seconds() >= 3600:
            last_pm = now
            try:
                n = run_postmortems(STATE, fetch_for)
                if n:
                    print(f"[brain {now:%m-%d %H:%M}] journal: {n} post-mortems written",
                          flush=True)
            except Exception as e:
                print(f"[brain] WARN postmortem: {e}", flush=True)

        boundary = now.replace(minute=0, second=0, microsecond=0,
                               hour=(now.hour // 4) * 4)
        if last_4h is None or boundary > last_4h:
            last_4h = boundary
            print(f"[brain {now:%m-%d %H:%M}] 4h close {boundary:%H:%M} -> discovery pass",
                  flush=True)
            try:
                for line in discovery_pass(cfg, STATE, NAME, start_bal, fetch_for, symbols):
                    print(f"  [disc] {line}", flush=True)
            except Exception as e:
                print(f"[brain] WARN discovery: {e}", flush=True)
        time.sleep(CHECK_EVERY)


if __name__ == "__main__":
    main()
