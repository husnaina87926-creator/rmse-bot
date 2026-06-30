"""Weekly self-improvement brain (wired to the 3-account bot).

1) Discover a robust NEW candidate edge per instrument (gold/BTC/ETH) -> state/candidates.json
   (each then forward-tests in a challenger account via run_bots).
2) Promotion check: if a challenger has beaten its champion over enough FORWARD trades,
   promote its candidate into state/live_rules.json (the bot reads these). Overfit
   candidates fail the forward gate and are never promoted.
Writes reports/learning_<date>.md. Run from project root: python scripts/run_self_learning.py
"""
import sys
import os
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import fetch_dukascopy
from rmse_bot.binance_feed import fetch_binance_klines
from rmse_bot.paper_trader import load_state, new_state, save_state
from rmse_bot.self_improve import (
    load_live_rules, save_live_rules, rules_for, top_candidate, should_promote,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
REPORTS = os.path.join(ROOT, "reports")
NAME = {"XAUUSD": "gold", "BTCUSDT": "btc", "ETHUSDT": "eth", "SOLUSDT": "sol",
        "ADAUSDT": "ada", "DOGEUSDT": "doge", "OPUSDT": "op", "SEIUSDT": "sei",
        "VETUSDT": "vet", "GALAUSDT": "gala", "XTZUSDT": "xtz", "SANDUSDT": "sand",
        "MANAUSDT": "mana", "HBARUSDT": "hbar"}
MIN_FWD_TRADES = 30


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    now = dt.datetime.now(dt.timezone.utc)
    start_bal = cfg["account"]["size_usd"]
    live = load_live_rules(os.path.join(STATE, "live_rules.json"))
    cand_path = os.path.join(STATE, "candidates.json")
    candidates = json.load(open(cand_path)) if os.path.exists(cand_path) else {}
    symbols = ["XAUUSD"] + list(cfg["crypto_rules"]["symbols"])
    md = [f"# Self-Improvement Report — {now:%Y-%m-%d}\n",
          "_Discover candidates -> forward-test as challengers -> promote only if they beat champion live._\n"]

    # --- 1. promotion check (forward-proven candidates) ---
    promoted = []
    for sym in symbols:
        nm = NAME[sym]
        champ = load_state(os.path.join(STATE, f"{nm}.json"), start_bal)
        chal_path = os.path.join(STATE, f"{nm}_chal.json")
        if not os.path.exists(chal_path) or sym not in candidates:
            continue
        chal = load_state(chal_path, start_bal)
        if should_promote(champ, chal, start_bal, MIN_FWD_TRADES):
            live[sym] = rules_for(sym, cfg, live) + [candidates[sym]["rule"]]
            promoted.append((sym, candidates[sym]["rule"]))
            candidates.pop(sym, None)
            os.remove(chal_path)                 # reset; a fresh candidate will be tested next
    if promoted:
        save_live_rules(live, os.path.join(STATE, "live_rules.json"))
    md.append(f"\n## Promotions this run: {len(promoted)}\n")
    for sym, r in promoted:
        md.append(f"  - {sym}: PROMOTED `{r['direction']} {' & '.join(r['when'])}` (beat champion on forward data)\n")

    # --- 2. discover fresh candidates per instrument ---
    md.append("\n## Candidate discovery\n")
    for sym in symbols:
        try:
            if sym == "XAUUSD":
                df = fetch_dukascopy(sym, "15m", now - dt.timedelta(days=500), now)
            else:
                df = fetch_binance_klines(sym, "4h", now - dt.timedelta(days=1000), now)
        except Exception as e:
            md.append(f"  - {sym}: data fetch failed ({e})\n")
            continue
        cur = rules_for(sym, cfg, live)
        cand = top_candidate(sym, df, cfg, cur)
        if cand:
            # only reset the challenger if the candidate changed
            if candidates.get(sym, {}).get("rule") != cand["rule"]:
                p = os.path.join(STATE, f"{NAME[sym]}_chal.json")
                if os.path.exists(p):
                    os.remove(p)
            candidates[sym] = cand
            md.append(f"  - {sym}: candidate `{cand['rule']['direction']} {' & '.join(cand['rule']['when'])}`"
                      f" (backtest ret ${cand['return']}, PF {cand['pf']}) -> forward-testing\n")
        else:
            md.append(f"  - {sym}: no new robust candidate\n")

    os.makedirs(STATE, exist_ok=True)
    os.makedirs(REPORTS, exist_ok=True)
    with open(cand_path, "w") as f:
        json.dump(candidates, f, indent=2)
    with open(os.path.join(REPORTS, f"learning_{now:%Y-%m-%d}.md"), "w") as f:
        f.write("".join(md))
    print("".join(md))


if __name__ == "__main__":
    main()
