import pandas as pd
from rmse_bot.config import load_config
from rmse_bot.paper_trader import (
    new_state, save_state, load_state,
    scan_for_entries, manage_open_positions,
)


def _uptrend(n=300, start=1000.0, step=0.5):
    close = [start + step * i for i in range(n)]
    return pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
        "open": close,
        "high": [c + 1.0 for c in close],
        "low": [c - 1.0 for c in close],
        "close": close,
    })


def test_scan_opens_a_trade_on_signal():
    cfg = load_config("config.yaml")
    rules = {"XAUUSD": [{"direction": "buy", "when": ["trend_up"]}]}
    state = new_state(100)
    scan_for_entries(state, {"XAUUSD": _uptrend()}, cfg, rules)
    assert len(state["open"]) == 1
    pos = state["open"][0]
    assert pos["direction"] == "buy"
    assert pos["sl"] < pos["entry"] < pos["tp"]
    assert pos["margin"] > 0


def test_manage_closes_on_take_profit():
    cfg = load_config("config.yaml")
    state = new_state(100)
    state["open"].append({
        "symbol": "XAUUSD", "direction": "buy", "entry": 1000.0,
        "sl": 990.0, "tp": 1010.0, "lots": 0.01,
        "open_time": "2024-01-01 00:00:00+00:00", "cost": 0.0, "margin": 0.2,
    })
    # later bars: one reaches the TP (high >= 1010)
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01 00:15", periods=3, freq="15min", tz="UTC"),
        "open": [1001, 1004, 1009.0],
        "high": [1003, 1006, 1011.0],
        "low": [1000, 1003, 1008.0],
        "close": [1002, 1005, 1010.0],
    })
    manage_open_positions(state, {"XAUUSD": df}, cfg)
    assert len(state["open"]) == 0
    assert state["closed"][0]["outcome"] == "tp"
    assert state["balance"] > 100         # profit booked (gross 10*100*0.01 = $10)


def test_state_persistence(tmp_path):
    p = tmp_path / "state.json"
    s = new_state(100)
    s["balance"] = 123.45
    save_state(s, str(p))
    loaded = load_state(str(p), 100)
    assert loaded["balance"] == 123.45
