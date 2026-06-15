"""Champion vs Challenger forward testing.

The 'champion' is the live strategy. Each 'challenger' is the champion PLUS one
candidate rule from the self-learning registry, run in its own parallel virtual
account on the SAME live data. After enough forward time, if a challenger beats the
champion on new (un-overfit) data, it's a real promotion. This is how we add edges
safely instead of trusting backtests that may be overfit.
"""
import copy


def build_accounts(cfg: dict, registry: dict = None, max_challengers: int = 3) -> list:
    """Champion account + one challenger per self-learning promotion candidate."""
    champ_rules = cfg.get("edge_rules", {})
    accounts = [{"name": "champion", "rules": champ_rules, "state": "state/paper_state.json"}]
    if not registry:
        return accounts
    for i, p in enumerate(registry.get("promotions", [])[:max_challengers], 1):
        sym = p.get("symbol")
        if sym not in champ_rules:        # symbol no longer traded (e.g. EURUSD dropped)
            continue
        rules = copy.deepcopy(champ_rules)
        rules[sym] = rules[sym] + [{"direction": p["direction"], "when": list(p["candidate"])}]
        accounts.append({
            "name": f"challenger_{i}",
            "rules": rules,
            "state": f"state/challenger_{i}.json",
            "added": {"symbol": sym, "when": list(p["candidate"]), "direction": p["direction"]},
        })
    return accounts


def compare_accounts(named_states: list) -> list:
    """named_states: list of (name, state_dict). Returns per-account metrics."""
    rows = []
    for name, s in named_states:
        closed = s.get("closed", [])
        wins = [t for t in closed if t["pnl"] > 0]
        wr = len(wins) / len(closed) if closed else 0.0
        rows.append({
            "name": name,
            "balance": round(s.get("balance", 0.0), 2),
            "trades": len(closed),
            "open": len(s.get("open", [])),
            "win": round(wr, 2),
            "pnl": round(sum(t["pnl"] for t in closed), 2),
        })
    return rows
