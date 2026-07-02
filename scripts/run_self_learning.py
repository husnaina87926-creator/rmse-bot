"""Weekly self-improvement brain (GitHub Actions; the VPS runs the same passes
continuously via scripts/run_brain_live.py).

1) DEMOTION: un-learn any promoted rule whose forward record since promotion decayed.
2) PROMOTION: promote candidates that beat their champion over 30+ FORWARD trades with a
   statistically meaningful edge (t-stat gate) -> state/live_rules.json (+ promotions.json).
3) DISCOVERY (with candidate stickiness): refresh candidates per instrument; a candidate
   keeps its challenger until it has had a fair forward trial.
Writes reports/learning_<date>.md. Run from project root: python scripts/run_self_learning.py
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import fetch_dukascopy
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.self_improve import promotion_demotion_pass, discovery_pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
REPORTS = os.path.join(ROOT, "reports")
NAME = {"XAUUSD": "gold", "BTCUSDT": "btc", "ETHUSDT": "eth", "SOLUSDT": "sol",
        "ADAUSDT": "ada", "DOGEUSDT": "doge", "OPUSDT": "op", "SEIUSDT": "sei",
        "VETUSDT": "vet", "GALAUSDT": "gala", "XTZUSDT": "xtz", "SANDUSDT": "sand",
        "MANAUSDT": "mana", "HBARUSDT": "hbar"}


def fetch_for(sym):
    now = dt.datetime.now(dt.timezone.utc)
    if sym == "XAUUSD":
        return fetch_dukascopy(sym, "15m", now - dt.timedelta(days=500), now)
    return fetch_binance_klines(sym, "4h", now - dt.timedelta(days=1000), now)


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    now = dt.datetime.now(dt.timezone.utc)
    start_bal = cfg["account"]["size_usd"]
    symbols = ["XAUUSD"] + list(cfg["crypto_rules"]["symbols"])
    md = [f"# Self-Improvement Report — {now:%Y-%m-%d}\n",
          "_Demote decayed -> promote forward-proven (t-stat gate) -> discover (sticky candidates)._\n"]

    promoted, demoted = promotion_demotion_pass(cfg, STATE, NAME, start_bal)
    md.append(f"\n## Demotions this run: {len(demoted)}\n")
    for sym, r in demoted:
        md.append(f"  - {sym}: DEMOTED `{r['direction']} {' & '.join(r['when'])}` (forward decay)\n")
    md.append(f"\n## Promotions this run: {len(promoted)}\n")
    for sym, r in promoted:
        md.append(f"  - {sym}: PROMOTED `{r['direction']} {' & '.join(r['when'])}` (beat champion forward, t-stat passed)\n")

    md.append("\n## Candidate discovery\n")
    for line in discovery_pass(cfg, STATE, NAME, start_bal, fetch_for, symbols):
        md.append(f"  - {line}\n")

    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, f"learning_{now:%Y-%m-%d}.md"), "w") as f:
        f.write("".join(md))
    print("".join(md))


if __name__ == "__main__":
    main()
