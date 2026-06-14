import pandas as pd
from rmse_bot.config import load_config
from rmse_bot.backtest import (
    simulate_trade, simulate_trade_dynamic, compute_metrics, backtest_edge, walk_forward,
)


def test_dynamic_trailing_locks_profit():
    # buy: trail 1*ATR(5)=5 behind best; price runs to ~120 then pulls back to 115
    future = pd.DataFrame({
        "high": [106, 121, 117], "low": [104, 119, 115], "close": [105, 120, 116],
    }, dtype=float)
    label, exit_price = simulate_trade_dynamic(
        "buy", entry=100, sl=95, tp=200, atr_val=5.0, future=future, trail_atr=1.0)
    assert exit_price == 116          # stopped out at trailed stop (best 121 - 5)
    assert label == "win"             # locked above entry


def test_dynamic_breakeven_moves_stop_to_entry():
    # buy: BE trigger 1*ATR(5) -> at +5 move stop to entry(100); then dips to 100
    future = pd.DataFrame({
        "high": [106, 101], "low": [98, 99], "close": [105, 100],
    }, dtype=float)
    label, exit_price = simulate_trade_dynamic(
        "buy", entry=100, sl=90, tp=200, atr_val=5.0, future=future, be_trigger_atr=1.0)
    assert exit_price == 100          # stopped at break-even, not the original 90


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


def test_backtest_edge_produces_trades():
    cfg = load_config("config.yaml")
    instr = cfg["instruments"]["XAUUSD"]
    n = 500
    close = [1000 + i * 0.5 for i in range(n)]   # steady uptrend -> trend_up true
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
        "open": close,
        "high": [c + 1.0 for c in close],
        "low": [c - 1.0 for c in close],
        "close": close,
    })
    rules = [{"direction": "buy", "when": ["trend_up"]}]
    res = backtest_edge(df, cfg, instr, rules, lookback=250, max_hold=12)
    assert res.metrics["num_trades"] > 0
    assert "profit_factor" in res.metrics


def test_walk_forward_returns_folds():
    cfg = load_config("config.yaml")
    instr = cfg["instruments"]["XAUUSD"]
    n = 6000
    close = [1000 + i * 0.2 for i in range(n)]   # uptrend so trend_up rule fires
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
        "open": close,
        "high": [c + 1.0 for c in close],
        "low": [c - 1.0 for c in close],
        "close": close,
    })
    rules = [{"direction": "buy", "when": ["trend_up"]}]
    folds = walk_forward(df, cfg, instr, rules, train_len=3000, test_len=1000,
                         param_grid=[(2.0, 1.0, 24)], min_train_trades=5)
    assert len(folds) >= 1
    assert "test_pf" in folds[0] and "test_return" in folds[0]
