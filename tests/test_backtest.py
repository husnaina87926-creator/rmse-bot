import pandas as pd
from rmse_bot.backtest import simulate_trade, compute_metrics


def test_simulate_trade_hits_tp():
    # buy entry 100, sl 95, tp 110; highs reach 110 before low hits 95
    future = pd.DataFrame({"high": [101, 105, 111], "low": [99, 98, 109]}, dtype=float)
    assert simulate_trade("buy", entry=100, sl=95, tp=110, future=future) == "tp"


def test_simulate_trade_hits_sl():
    future = pd.DataFrame({"high": [101, 102], "low": [99, 94]}, dtype=float)
    assert simulate_trade("buy", 100, 95, 110, future) == "sl"


def test_simulate_trade_sell_hits_tp():
    # sell entry 100, sl 105, tp 90; low reaches 90 first
    future = pd.DataFrame({"high": [101, 99], "low": [98, 89]}, dtype=float)
    assert simulate_trade("sell", 100, 105, 90, future) == "tp"


def test_metrics_basic():
    trades = [{"pnl": 2.0}, {"pnl": 2.0}, {"pnl": -1.0}]
    m = compute_metrics(trades, start_balance=100)
    assert m["num_trades"] == 3
    assert round(m["win_rate"], 4) == round(2 / 3, 4)
    assert round(m["profit_factor"], 2) == 4.0     # gains 4 / losses 1
    assert round(m["total_return"], 2) == 3.0


def test_metrics_empty():
    m = compute_metrics([], start_balance=100)
    assert m["num_trades"] == 0
