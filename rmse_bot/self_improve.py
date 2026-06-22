"""Self-improvement loop wired to the 3-account bot (SAFE).

Weekly: discover a robust NEW candidate edge per instrument (gold/BTC/ETH). Each
candidate runs in a CHALLENGER account (champion rules + candidate) alongside the
champion, forward-testing on live data. A candidate is PROMOTED into the live rules
only after it beats its champion over enough FORWARD trades — so overfit candidates
(which look great on backtest but fail forward) never get promoted. Live rules live in
state/live_rules.json (mutable); the bot reads them, falling back to config.
"""
import json
import os

from rmse_bot.strategy_generator import generate_strategies


def load_live_rules(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_live_rules(rules: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(rules, f, indent=2)


def rules_for(symbol: str, cfg: dict, live: dict) -> list:
    """Current live rules for a symbol: promoted live_rules, else config default."""
    if symbol in live:
        return live[symbol]
    if symbol in cfg.get("edge_rules", {}):
        return cfg["edge_rules"][symbol]
    return cfg.get("crypto_rules", {}).get("rules", [])


def top_candidate(symbol: str, df, cfg: dict, current_rules: list, min_count: int = 80) -> dict:
    """Best robust NEW strategy (positive, distinct entry from current rules) or None."""
    cur = {frozenset(r["when"]) for r in current_rules}
    for s in generate_strategies(df, cfg, symbol, max_entries=8, min_count=min_count):
        if s["return"] > 0 and frozenset(s["entry"]) not in cur:
            rule = {"direction": s["direction"], "when": s["entry"]}
            if symbol != "XAUUSD":           # crypto rules are regime-specific
                rule["regime"] = "down" if s["direction"] == "sell" else "up"
            return {"rule": rule, "score": s["score"], "return": s["return"], "pf": s["pf"]}
    return None


def should_promote(champ_state: dict, chall_state: dict, start_bal: float,
                   min_trades: int = 30) -> bool:
    """Promote only after the challenger has enough FORWARD trades AND is profitable
    AND beats the champion's profit. Forward proof — not backtest."""
    if len(chall_state.get("closed", [])) < min_trades:
        return False
    champ_pnl = champ_state.get("balance", start_bal) - start_bal
    chall_pnl = chall_state.get("balance", start_bal) - start_bal
    return chall_pnl > 0 and chall_pnl > champ_pnl
