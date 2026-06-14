import numpy as np
import pandas as pd
from rmse_bot.config import load_config
from rmse_bot.self_learning import (
    current_conditions, candidate_rules, evaluate_challenger,
)


def test_current_conditions_reads_strategy():
    cfg = load_config("config.yaml")
    cur = current_conditions(cfg, "XAUUSD")
    assert ("high_vol", "rsi_overbought", "trend_up") in cur   # sorted tuple of the rule


def test_candidate_rules_filters_new_robust_only():
    registry = [
        {"conditions": ["rsi_overbought", "high_vol"], "net_oos": 0.12,
         "holds": True, "bias": "UP", "in_strategy": True},     # already used -> skip
        {"conditions": ["sweep_up", "session_ny"], "net_oos": 0.09,
         "holds": True, "bias": "UP", "in_strategy": False},    # NEW robust -> keep
        {"conditions": ["bull_engulf"], "net_oos": 0.01,
         "holds": False, "bias": "UP", "in_strategy": False},   # weak / not held -> skip
    ]
    cands = candidate_rules(registry, edge_min=0.05)
    assert len(cands) == 1
    assert cands[0]["when"] == ["sweep_up", "session_ny"]
    assert cands[0]["direction"] == "buy"


def test_evaluate_challenger_runs_and_reports_verdict():
    cfg = load_config("config.yaml")
    n = 1200
    rng = np.random.default_rng(1)
    steps = rng.normal(0, 1, n).cumsum() + 2000
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
        "open": steps,
        "high": steps + rng.uniform(0.1, 2.0, n),
        "low": steps - rng.uniform(0.1, 2.0, n),
        "close": steps + rng.normal(0, 0.3, n),
    })
    candidate = {"direction": "buy", "when": ["rsi_oversold", "high_vol"]}
    res = evaluate_challenger("XAUUSD", df, cfg, candidate)
    assert res["verdict"] in ("PROMOTE-CANDIDATE", "reject")
    assert "champ_return" in res and "chall_return" in res
