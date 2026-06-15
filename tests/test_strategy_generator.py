import pandas as pd
from rmse_bot.config import load_config
from rmse_bot.strategy_generator import robustness_consistency, evaluate_strategy


def test_robustness_consistency_all_profitable():
    trades = [{"pnl": 1.0}] * 8        # every window profitable
    assert robustness_consistency(trades, n_windows=4) == 1.0


def test_robustness_consistency_one_lucky_window():
    # all profit in the last window, losses elsewhere -> low consistency
    trades = [{"pnl": -1.0}] * 6 + [{"pnl": 20.0}, {"pnl": 20.0}]
    c = robustness_consistency(trades, n_windows=4)
    assert c <= 0.5


def test_evaluate_strategy_returns_metrics_or_none():
    cfg = load_config("config.yaml")
    instr = cfg["instruments"]["XAUUSD"]
    n = 500
    close = [1000 + i * 0.3 for i in range(n)]   # uptrend so trend_up fires often
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
        "open": close,
        "high": [c + 1.0 for c in close],
        "low": [c - 1.0 for c in close],
        "close": close,
    })
    ev = evaluate_strategy(df, cfg, instr, [{"direction": "buy", "when": ["trend_up"]}],
                           {"sl_atr": 2.0, "rr": 1.0, "max_hold": 24, "be_atr": 1.0},
                           min_trades=5)
    assert ev is None or ("score" in ev and "consistency" in ev and "return" in ev)
