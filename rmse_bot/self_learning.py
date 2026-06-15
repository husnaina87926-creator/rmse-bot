"""Self-learning core (SAFE).

The bot periodically re-mines the data for edges, records EVERYTHING in a candidate
registry (incl. conditions NOT in the current strategy), and for each robust NEW
candidate runs a champion-vs-challenger backtest to see if ADDING it would help.

It does NOT blindly edit the live strategy (that path = overfitting ruin). It produces
recommendations + an audit trail; promotion stays a deliberate, forward-tested step.
"""
from rmse_bot.discovery import (
    run_discovery, run_combo_discovery,
    build_features, triple_barrier_labels, walk_forward_edges,
)
from rmse_bot.backtest import backtest_edge

# exit/strategy config validated earlier (break-even, 1:1, 6h hold)
DEFAULT_EXIT = {"sl_atr": 2.0, "rr": 1.0, "max_hold": 24, "be_atr": 1.0}


def current_conditions(cfg: dict, symbol: str) -> set:
    """Condition-sets already used by the live strategy for this symbol."""
    return {tuple(sorted(r["when"])) for r in cfg.get("edge_rules", {}).get(symbol, [])}


def build_registry(symbol: str, df, cfg: dict, min_count: int = 300) -> list:
    """Every condition/combo with its OOS edge, single-split holds, AND walk-forward
    robustness (does the edge survive across many windows). 'note everything' registry."""
    cur = current_conditions(cfg, symbol)
    feats = build_features(df)
    labels = triple_barrier_labels(df)
    rows = []

    def add(conds, net_oos, holds, bias):
        # walk-forward only for single-split survivors (cheap + that's all candidates need)
        wf = walk_forward_edges(feats, labels, list(conds)) if holds else {"wf_pass": False, "consistency": 0.0}
        rows.append({
            "symbol": symbol, "conditions": list(conds), "net_oos": net_oos,
            "holds": holds, "wf_pass": bool(wf["wf_pass"]),
            "wf_consistency": wf["consistency"], "bias": bias,
            "in_strategy": tuple(sorted(conds)) in cur,
        })

    singles = run_discovery(df, split=0.7, min_count=min_count)
    for _, r in singles.iterrows():
        net = float(r["oos_net"]) if r["oos_net"] == r["oos_net"] else 0.0
        add((r["condition"],), net, bool(r["holds"]), "UP" if r["net"] > 0 else "DOWN")

    combos = run_combo_discovery(df, split=0.7, sizes=(2, 3), min_count=min_count)
    for _, r in combos.iterrows():
        net = float(r["net_oos"]) if r["net_oos"] == r["net_oos"] else 0.0
        conds = tuple(c.strip() for c in r["conditions"].split("&"))
        add(conds, net, bool(r["holds"]), r["bias"])

    return rows


def candidate_rules(registry: list, edge_min: float = 0.05) -> list:
    """Robust NEW candidates: must pass WALK-FORWARD (edge survives across windows),
    not already used, meaningful edge. Walk-forward is the stronger overfitting guard
    that single-split 'holds' missed."""
    out = []
    for r in registry:
        if r.get("wf_pass") and not r["in_strategy"] and abs(r["net_oos"]) >= edge_min:
            out.append({
                "direction": "buy" if r["bias"] == "UP" else "sell",
                "when": r["conditions"],
                "net_oos": r["net_oos"],
                "wf_consistency": r.get("wf_consistency", 0.0),
            })
    return out


def evaluate_challenger(symbol: str, df, cfg: dict, candidate: dict,
                        exit_cfg: dict = None) -> dict:
    """Backtest champion (current rules) vs challenger (current + candidate rule).
    'PROMOTE?' only if the challenger raises return without hurting profit factor."""
    exit_cfg = exit_cfg or DEFAULT_EXIT
    instr = cfg["instruments"][symbol]
    champ = cfg["edge_rules"][symbol]
    challenger = champ + [{"direction": candidate["direction"], "when": candidate["when"]}]

    cm = backtest_edge(df, cfg, instr, champ, **exit_cfg).metrics
    hm = backtest_edge(df, cfg, instr, challenger, **exit_cfg).metrics
    pf_c = cm["profit_factor"] if cm["profit_factor"] != float("inf") else 9.99
    pf_h = hm["profit_factor"] if hm["profit_factor"] != float("inf") else 9.99
    improved = (hm["total_return"] > cm["total_return"]) and (pf_h >= pf_c * 0.95)
    return {
        "symbol": symbol,
        "candidate": candidate["when"],
        "direction": candidate["direction"],
        "champ_pf": round(pf_c, 2), "chall_pf": round(pf_h, 2),
        "champ_return": round(cm["total_return"], 2),
        "chall_return": round(hm["total_return"], 2),
        "verdict": "PROMOTE-CANDIDATE" if improved else "reject",
    }
