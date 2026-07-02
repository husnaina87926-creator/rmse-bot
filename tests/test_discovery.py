import numpy as np
import pandas as pd
from rmse_bot.discovery import (
    triple_barrier_labels, build_features, discover_edges,
    run_combo_discovery, walk_forward_edges, _bull_engulf,
)


def test_walk_forward_edges_consistent_passes():
    n = 500
    feats = pd.DataFrame({"cond": [True] * n})
    labels = pd.Series([1] * n)            # up move every window -> consistent edge
    res = walk_forward_edges(feats, labels, ["cond"], n_windows=5, min_count=10)
    assert res["wf_pass"] is True
    assert res["consistency"] == 1.0


def test_walk_forward_edges_inconsistent_fails():
    n = 500
    feats = pd.DataFrame({"cond": [True] * n})
    labels = pd.Series([1] * 250 + [-1] * 250)   # sign flips across windows -> not robust
    res = walk_forward_edges(feats, labels, ["cond"], n_windows=5, min_count=10)
    assert res["wf_pass"] is False


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


def test_run_combo_discovery_structure():
    # noisy random-walk df so combos have varied counts; just check it runs + shape
    rng = np.random.default_rng(0)
    n = 1500
    steps = rng.normal(0, 1, n).cumsum() + 1000
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC"),
        "open": steps,
        "high": steps + rng.uniform(0.1, 1.0, n),
        "low": steps - rng.uniform(0.1, 1.0, n),
        "close": steps + rng.normal(0, 0.2, n),
    })
    res = run_combo_discovery(df, split=0.7, sizes=(2,), min_count=20,
                              oos_min_count=10, edge_min=0.05)
    for col in ["conditions", "size", "net_is", "net_oos", "bias", "holds"]:
        assert col in res.columns
    assert res["holds"].dtype == bool


def test_z_threshold_and_net_z():
    from rmse_bot.discovery import _z_threshold, _net_z
    assert abs(_z_threshold(0.05) - 1.645) < 0.01           # one-sided 5%
    assert abs(_z_threshold(0.0005) - 3.29) < 0.01          # Bonferroni 0.05/100
    assert _z_threshold(0.0005) > _z_threshold(0.05)        # more tests -> higher bar
    # net edge 0.2 over 100 samples: var = 1.0 - 0.04, z ~ 2.04
    assert abs(_net_z(0.6, 0.4, 100) - 2.041) < 0.01
    assert _net_z(0.5, 0.5, 100) == 0.0                     # no edge -> z 0
    assert _net_z(1.0, 0.0, 50) == float("inf")             # zero variance, pure signal


def test_walk_forward_purge_blocks_boundary_leak():
    # each 100-bar window: bars 0-87 alternate +1/-1 (zero net), bars 88-99 all +1 —
    # exactly the label-horizon tail whose labels resolve in the NEXT window
    n = 500
    labels = pd.Series([1 if (i % 100) >= 88 else (1 if i % 2 == 0 else -1)
                        for i in range(n)])
    feats = pd.DataFrame({"cond": [True] * n})
    leaky = walk_forward_edges(feats, labels, ["cond"], n_windows=5,
                               min_count=10, purge=0)
    assert leaky["wf_pass"] is True                          # leakage looks like an edge
    purged = walk_forward_edges(feats, labels, ["cond"], n_windows=5,
                                min_count=10, purge=12)
    assert purged["wf_pass"] is False                        # purge removes the mirage


def test_run_discovery_rigor_columns():
    from rmse_bot.discovery import run_discovery
    df = _ramp_df(100, 0.2, 1200)
    res = run_discovery(df, split=0.7, min_count=20)
    assert "z_is" in res.columns
    assert res["holds"].dtype == bool


def test_new_feature_angles_volume_weekend_btc(tmp_path):
    from rmse_bot.discovery import set_market_context
    n = 300
    df = _ramp_df(100, 0.2, n)
    df["time"] = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    df["volume"] = [100.0] * (n - 1) + [1000.0]                # spike on last bar
    try:
        # no context yet -> btc features exist but are all False
        feats = build_features(df)
        for col in ("vol_spike", "vol_quiet", "vol_rising", "weekend", "btc_up", "btc_down"):
            assert col in feats.columns
        assert feats.dtypes.apply(lambda d: d == bool).all()   # still all boolean
        assert bool(feats["vol_spike"].iloc[-1]) is True
        assert not feats["btc_up"].any() and not feats["btc_down"].any()
        assert feats["weekend"].any() and not feats["weekend"].all()
        # rising BTC daily context -> btc_up becomes true late in the window
        days = pd.date_range("2023-06-01", periods=300, freq="D", tz="UTC")
        btc = pd.DataFrame({"time": days, "open": range(300), "high": range(1, 301),
                            "low": range(300), "close": [100 + 2 * i for i in range(300)]})
        set_market_context(btc)
        feats = build_features(df)
        assert feats["btc_up"].iloc[-1] and not feats["btc_down"].any()
        # no volume column -> features exist, all False, still boolean
        feats2 = build_features(df.drop(columns=["volume"]))
        assert not feats2["vol_spike"].any()
        assert feats2.dtypes.apply(lambda d: d == bool).all()
    finally:
        set_market_context(None)                               # never leak into other tests
