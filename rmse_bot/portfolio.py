"""Portfolio / ensemble (Phase A power upgrade).

Instead of one strategy, run a PORTFOLIO of several robust, DISTINCT strategies. Many
weak-but-uncorrelated edges combine into a smoother, stronger system (lower drawdown) —
the real quant-fund principle. This adds power WITHOUT adding overfitting surface
(diversification reduces risk). Selection picks top robust strategies with different
entry logic (not exit-variants of the same entry).
"""
from rmse_bot.backtest import backtest_edge
from rmse_bot.strategy_generator import robustness_consistency

DEFAULT_EXIT = {"sl_atr": 2.0, "rr": 1.0, "max_hold": 24, "be_atr": 1.0}


def select_portfolio(strategies: list, max_n: int = 4) -> list:
    """Pick up to max_n top-score strategies with DISTINCT (direction, entry) sets."""
    seen, chosen = set(), []
    for s in strategies:                      # assumed sorted by score desc
        key = (s["direction"], frozenset(s["entry"]))
        if key in seen:
            continue
        seen.add(key)
        chosen.append(s)
        if len(chosen) >= max_n:
            break
    return chosen


def portfolio_rules(chosen: list) -> list:
    """Turn selected strategies into an edge_rules list (one entry rule each)."""
    return [{"direction": s["direction"], "when": list(s["entry"])} for s in chosen]


def evaluate(df, cfg, instr, rules, exit_cfg=None) -> dict:
    """Backtest a rule set (single strategy or whole portfolio) with robust metrics."""
    exit_cfg = exit_cfg or DEFAULT_EXIT
    res = backtest_edge(df, cfg, instr, rules, **exit_cfg)
    m = res.metrics
    consistency = robustness_consistency(res.trades)
    pf = m["profit_factor"] if m["profit_factor"] != float("inf") else 9.99
    return {
        "return": round(m["total_return"], 2), "pf": round(pf, 2),
        "win": round(m["win_rate"], 2), "maxdd": round(m["max_drawdown"], 2),
        "trades": m["num_trades"], "consistency": consistency,
        "score": round(m["total_return"] * consistency, 2),
    }
