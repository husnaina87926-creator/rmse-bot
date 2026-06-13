import pandas as pd
from rmse_bot.discovery import (
    triple_barrier_labels, build_features, discover_edges,
    _bull_engulf,
)


def _ramp_df(start, step, n):
    close = [start + step * i for i in range(n)]
    return pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
        "open": close,
        "high": [c + 0.5 for c in close],
        "low": [c - 0.5 for c in close],
        "close": close,
    })


def test_triple_barrier_up_ramp_labels_up():
    df = _ramp_df(100, 1.0, 40)
    labels = triple_barrier_labels(df, horizon=12, k_atr=1.5, atr_period=3)
    assert labels.iloc[15] == 1     # steady rise -> upper barrier hit first


def test_triple_barrier_down_ramp_labels_down():
    df = _ramp_df(200, -1.0, 40)
    labels = triple_barrier_labels(df, horizon=12, k_atr=1.5, atr_period=3)
    assert labels.iloc[15] == -1


def test_bull_engulf_detects_pattern():
    df = pd.DataFrame({
        "open": [10.0, 8.5],
        "high": [10.2, 10.6],
        "low": [8.8, 8.4],
        "close": [9.0, 10.5],   # bar0 bearish, bar1 bullish engulfing
    })
    out = _bull_engulf(df)
    assert bool(out.iloc[1]) is True
    assert bool(out.iloc[0]) is False


def test_discover_edges_finds_perfect_predictor():
    # 'cond' is True for the first 60 rows (all up moves), False for next 60 (all down)
    n = 120
    feats = pd.DataFrame({"cond": [True] * 60 + [False] * 60})
    labels = pd.Series([1] * 60 + [-1] * 60)
    res = discover_edges(feats, labels, min_count=10)
    row = res[res["condition"] == "cond"].iloc[0]
    assert row["p_up"] == 1.0
    assert row["p_dn"] == 0.0
    assert row["net"] == 1.0


def test_build_features_returns_boolean_columns():
    df = _ramp_df(100, 0.2, 300)
    feats = build_features(df)
    assert "sweep_down" in feats.columns
    assert "session_london" in feats.columns
    assert feats.dtypes.apply(lambda d: d == bool).all()
