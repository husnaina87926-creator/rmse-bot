"""Self-contained strategy generator (no external LLM).

The bot composes its OWN strategies from trading building blocks — entry condition-sets
that survived walk-forward, crossed with a grid of exit configs (RR / hold / break-even)
— backtests each, and ranks them by ROBUST profit (total return x consistency across
time windows), NOT raw win rate. Output is a leaderboard for the human to choose from;
the chosen one then goes to a forward-test challenger before any promotion.

Overfitting guard: entries are already walk-forward-robust; ranking rewards CONSISTENCY
(profitable in most windows), so one-lucky-window strategies sink. Forward-testing is
still the final judge.
"""
from rmse_bot.backtest import backtest_edge
from rmse_bot.self_learning import build_registry, candidate_rules

EXIT_GRID = [
    {"sl_atr": 2.0, "rr": rr, "max_hold": 24, "be_atr": be}
    for rr in (0.75, 1.0, 1.5) for be in (0.0, 1.0)
]


def robustness_consistency(trades: list, n_windows: int = 4) -> float:
    """Fraction of equal time-windows that were net profitable. Rewards strategies
    that work across periods, punishes one-lucky-window flukes."""
    pnls = [t["pnl"] for t in trades]
    if not pnls:
        return 0.0
    size = max(1, len(pnls) // n_windows)
    profitable = 0
    for w in range(n_windows):
        hi = len(pnls) if w == n_windows - 1 else (w + 1) * size
        seg = pnls[w * size:hi]
        if seg and sum(seg) > 0:
            profitable += 1
    return profitable / n_windows


def evaluate_strategy(df, cfg, instr, rules, exit_cfg, min_trades: int = 30):
    """Backtest one strategy; return robust metrics or None if too few trades."""
    res = backtest_edge(df, cfg, instr, rules, **exit_cfg)
    m = res.metrics
    if m["num_trades"] < min_trades:
        return None
    consistency = robustness_consistency(res.trades)
    pf = m["profit_factor"] if m["profit_factor"] != float("inf") else 9.99
    return {
        "return": round(m["total_return"], 2), "pf": round(pf, 2),
        "win": round(m["win_rate"], 2), "maxdd": round(m["max_drawdown"], 2),
        "trades": m["num_trades"], "consistency": consistency,
        "score": round(m["total_return"] * consistency, 2),   # robust profit
    }


def generate_strategies(df, cfg, symbol, max_entries: int = 8, min_count: int = 200) -> list:
    """Compose entry ideas (champion + walk-forward-robust candidates) x exit grid,
    backtest each, return a leaderboard sorted by robust-profit score (desc)."""
    instr = cfg["instruments"][symbol]
    ideas = [(r["direction"], tuple(r["when"])) for r in cfg["edge_rules"].get(symbol, [])]
    for c in candidate_rules(build_registry(symbol, df, cfg, min_count=min_count)):
        ideas.append((c["direction"], tuple(c["when"])))

    seen, uniq = set(), []
    for d, w in ideas:
        key = (d, tuple(sorted(w)))
        if key not in seen:
            seen.add(key)
            uniq.append((d, w))
    uniq = uniq[:max_entries]

    results = []
    for d, w in uniq:
        for ex in EXIT_GRID:
            ev = evaluate_strategy(df, cfg, instr, [{"direction": d, "when": list(w)}], ex)
            if ev:
                ev.update({"direction": d, "entry": list(w),
                           "exit": {"rr": ex["rr"], "be": ex["be_atr"], "hold": ex["max_hold"]}})
                results.append(ev)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results
