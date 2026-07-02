"""Move Discovery engine.

Idea (user's): for every significant up/down move, look at the market *conditions
that preceded it*, then find which conditions carry a real statistical edge.
Guarded against overfitting by an in-sample / out-of-sample split.

Pipeline:
  triple_barrier_labels(df)  -> +1 (up move), -1 (down move), 0 (neither)
  build_features(df)         -> boolean conditions present BEFORE each bar's move
  discover_edges(feat, lab)  -> per-condition probability of up/down + edge vs baseline
  run_discovery(df)          -> discover on in-sample, verify on out-of-sample
"""
from itertools import combinations
import numpy as np
import pandas as pd
from rmse_bot.indicators import ema, rsi, atr, adx


def triple_barrier_labels(df: pd.DataFrame, horizon: int = 12,
                          k_atr: float = 1.5, atr_period: int = 14) -> pd.Series:
    """Label each bar by which barrier (close ± k*ATR) the future hits first
    within `horizon` bars. +1 up, -1 down, 0 neither/ambiguous."""
    a = atr(df, atr_period).values
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    n = len(df)
    labels = np.zeros(n, dtype=int)
    for i in range(n):
        if np.isnan(a[i]) or a[i] == 0:
            continue
        upper = close[i] + k_atr * a[i]
        lower = close[i] - k_atr * a[i]
        end = min(n, i + 1 + horizon)
        for j in range(i + 1, end):
            hit_up = high[j] >= upper
            hit_dn = low[j] <= lower
            if hit_up and hit_dn:
                break          # ambiguous within one bar -> leave 0
            if hit_up:
                labels[i] = 1
                break
            if hit_dn:
                labels[i] = -1
                break
    return pd.Series(labels, index=df.index)


def _z_threshold(alpha: float) -> float:
    """One-sided normal z for tail probability `alpha` (bisection on erfc; no scipy).
    Used for the multiple-testing (Bonferroni) gate: alpha is divided by the number
    of conditions/combos actually tested before calling this."""
    from math import erfc, sqrt
    alpha = min(max(alpha, 1e-16), 0.5)
    lo, hi = 0.0, 10.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if 0.5 * erfc(mid / sqrt(2)) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _net_z(p_up: float, p_dn: float, count: int) -> float:
    """z-score of the net edge (p_up - p_dn) against zero. Each labelled sample is
    x in {+1, 0, -1}, so var(x) = (p_up + p_dn) - net^2."""
    net = p_up - p_dn
    var = (p_up + p_dn) - net * net
    if count <= 1 or var <= 0:
        return float("inf") if net != 0 else 0.0
    return abs(net) / ((var / count) ** 0.5)


def _bull_engulf(df: pd.DataFrame) -> pd.Series:
    po, pc = df["open"].shift(1), df["close"].shift(1)
    co, cc = df["open"], df["close"]
    cond = (pc < po) & (cc > co) & (cc >= po) & (co <= pc)
    return cond.fillna(False)


def _bear_engulf(df: pd.DataFrame) -> pd.Series:
    po, pc = df["open"].shift(1), df["close"].shift(1)
    co, cc = df["open"], df["close"]
    cond = (pc > po) & (cc < co) & (cc <= po) & (co >= pc)
    return cond.fillna(False)


def _sweep_down(df: pd.DataFrame, lookback: int = 3, ref: int = 20) -> pd.Series:
    """Price poked below recent support then closed back above it (failed breakdown)."""
    prior_low = df["low"].shift(lookback).rolling(ref).min()
    recent_low = df["low"].rolling(lookback).min()
    return ((recent_low < prior_low) & (df["close"] > prior_low)).fillna(False)


def _sweep_up(df: pd.DataFrame, lookback: int = 3, ref: int = 20) -> pd.Series:
    """Price poked above recent resistance then closed back below it (failed breakout)."""
    prior_high = df["high"].shift(lookback).rolling(ref).max()
    recent_high = df["high"].rolling(lookback).max()
    return ((recent_high > prior_high) & (df["close"] < prior_high)).fillna(False)


# optional cross-market context (BTC daily) — alts follow BTC, so BTC's regime is a
# legitimate extra "angle" for every symbol's discovery. When never set, the btc_up /
# btc_down features are simply False everywhere and rules using them can never fire.
_MARKET_CTX = {"btc_daily": None}


def set_market_context(btc_daily_df) -> None:
    """Provide BTC daily candles as shared context for feature building (optional)."""
    _MARKET_CTX["btc_daily"] = btc_daily_df


def _btc_regime_flags(dates: pd.Series):
    d = _MARKET_CTX.get("btc_daily")
    if d is None or len(d) < 120:
        return None
    close = d["close"]
    e = ema(close, 100)
    up = (close > e) & (e > e.shift(20))
    dn = (close < e) & (e < e.shift(20))
    idx = pd.to_datetime(d["time"]).dt.date
    up.index = idx
    dn.index = idx
    return (dates.map(up).fillna(False).astype(bool).values,
            dates.map(dn).fillna(False).astype(bool).values)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Boolean conditions describing the state at each bar (the 'why' candidates)."""
    out = pd.DataFrame(index=df.index)
    e200 = ema(df["close"], 200)
    e9 = ema(df["close"], 9)
    e21 = ema(df["close"], 21)
    r = rsi(df["close"], 14)
    a = atr(df, 14)

    out["trend_up"] = df["close"] > e200
    out["trend_down"] = df["close"] < e200
    out["ema_fast_above"] = e9 > e21
    out["ema_fast_below"] = e9 < e21
    out["rsi_oversold"] = r < 30
    out["rsi_overbought"] = r > 70
    out["rsi_bull"] = (r >= 50) & (r <= 70)
    out["rsi_bear"] = (r >= 30) & (r < 50)

    atr_med = a.rolling(100, min_periods=20).median()
    out["high_vol"] = a > atr_med
    out["low_vol"] = a <= atr_med

    adx_v = adx(df, 14)
    out["strong_trend"] = adx_v > 25          # regime: trending (vs choppy)
    out["weak_trend"] = adx_v <= 20

    hour = pd.to_datetime(df["time"]).dt.hour
    out["session_asia"] = (hour >= 0) & (hour < 7)
    out["session_london"] = (hour >= 7) & (hour < 13)
    out["session_ny"] = (hour >= 13) & (hour < 21)

    out["sweep_down"] = _sweep_down(df)
    out["sweep_up"] = _sweep_up(df)
    out["bull_engulf"] = _bull_engulf(df)
    out["bear_engulf"] = _bear_engulf(df)

    # volume angle (crypto feeds carry volume; feeds without it -> features stay False)
    if "volume" in df.columns:
        v = df["volume"].astype(float)
        vmed = v.rolling(50, min_periods=10).median()
        out["vol_spike"] = v > 2.0 * vmed
        out["vol_quiet"] = v < 0.5 * vmed
        out["vol_rising"] = v.rolling(5).mean() > v.rolling(20).mean()
    else:
        out["vol_spike"] = out["vol_quiet"] = out["vol_rising"] = False

    # calendar angle (crypto trades weekends on thinner books)
    out["weekend"] = pd.to_datetime(df["time"]).dt.dayofweek >= 5

    # cross-market angle: BTC's daily regime as context for every symbol
    flags = _btc_regime_flags(pd.to_datetime(df["time"]).dt.date)
    if flags is not None:
        out["btc_up"], out["btc_down"] = flags
    else:
        out["btc_up"] = out["btc_down"] = False
    return out.fillna(False)


def discover_edges(features: pd.DataFrame, labels: pd.Series,
                   min_count: int = 50) -> pd.DataFrame:
    """For each boolean condition, P(up move) and P(down move) vs the baseline."""
    base_up = float((labels == 1).mean())
    base_dn = float((labels == -1).mean())
    rows = []
    for col in features.columns:
        mask = features[col].astype(bool)
        cnt = int(mask.sum())
        if cnt < min_count:
            continue
        sub = labels[mask]
        p_up = float((sub == 1).mean())
        p_dn = float((sub == -1).mean())
        rows.append({
            "condition": col,
            "count": cnt,
            "p_up": round(p_up, 3),
            "p_dn": round(p_dn, 3),
            "edge_up": round(p_up - base_up, 3),
            "edge_dn": round(p_dn - base_dn, 3),
            "net": round(p_up - p_dn, 3),
        })
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values("net", ascending=False).reset_index(drop=True)
    res.attrs["base_up"] = round(base_up, 3)
    res.attrs["base_dn"] = round(base_dn, 3)
    return res


def run_discovery(df: pd.DataFrame, split: float = 0.7, horizon: int = 12,
                  k_atr: float = 1.5, min_count: int = 50, purge: int = None,
                  mt_alpha: float = 0.05) -> pd.DataFrame:
    """Discover edges on the first `split` of data, then verify each condition's
    net edge on the held-out remainder. Robust patterns hold in BOTH columns.
    RIGOR: (1) PURGE/EMBARGO — the last `purge` (default: label horizon) bars of the
    in-sample slice are dropped because their triple-barrier labels resolve using
    out-of-sample bars (leakage); the label-truncated tail of the OOS slice is dropped
    too. (2) MULTIPLE-TESTING — with many conditions tested some pass by luck, so a
    surviving edge must also clear a Bonferroni-deflated z-score (mt_alpha / n_tested)."""
    purge = horizon if purge is None else purge
    feats = build_features(df)
    labels = triple_barrier_labels(df, horizon=horizon, k_atr=k_atr)

    n = len(df)
    k = int(n * split)
    in_f, in_l = feats.iloc[:max(0, k - purge)], labels.iloc[:max(0, k - purge)]
    out_hi = max(k, n - purge)
    out_f, out_l = feats.iloc[k:out_hi], labels.iloc[k:out_hi]

    is_res = discover_edges(in_f, in_l, min_count=min_count)
    if is_res.empty:
        return is_res
    oos_full = discover_edges(out_f, out_l, min_count=1).set_index("condition")

    oos_net, oos_cnt = [], []
    for cond in is_res["condition"]:
        if cond in oos_full.index:
            oos_net.append(oos_full.loc[cond, "net"])
            oos_cnt.append(int(oos_full.loc[cond, "count"]))
        else:
            oos_net.append(float("nan"))
            oos_cnt.append(0)
    is_res = is_res.copy()
    is_res["oos_net"] = oos_net
    is_res["oos_count"] = oos_cnt
    # multiple-testing gate: Bonferroni across the conditions actually tested
    z_thr = _z_threshold(mt_alpha / max(1, len(is_res)))
    z_is = [_net_z(r["p_up"], r["p_dn"], r["count"]) for _, r in is_res.iterrows()]
    is_res["z_is"] = [round(z, 2) if z != float("inf") else z for z in z_is]
    # "holds" = a MEANINGFUL edge of the same sign in BOTH samples (not near-zero
    # noise) that is also statistically significant after the Bonferroni correction
    edge_min = 0.03
    is_res["holds"] = [
        (not np.isnan(o)) and (np.sign(o) == np.sign(n_))
        and abs(n_) >= edge_min and abs(o) >= edge_min and z >= z_thr
        for n_, o, z in zip(is_res["net"], is_res["oos_net"], z_is)
    ]
    return is_res


def walk_forward_edges(features: pd.DataFrame, labels: pd.Series, conditions: list,
                       n_windows: int = 5, min_count: int = 40,
                       edge_min: float = 0.05, purge: int = 12) -> dict:
    """Stronger-than-one-split test: does a condition-set's edge survive across MANY
    sequential time windows? Returns wf_pass (consistent same-sign edge in >=60% of
    windows), consistency, and mean net edge. This catches edges that pass a single
    OOS split by luck (overfitting) but don't hold across regimes.
    PURGED: each window's last `purge` bars (the label horizon) are excluded so a
    window's labels cannot resolve inside the next window — windows stay independent."""
    mask = features[list(conditions)].all(axis=1)
    n = len(features)
    size = max(1, n // n_windows)
    nets = []
    for w in range(n_windows):
        lo = w * size
        hi = n if w == n_windows - 1 else (w + 1) * size
        hi = max(lo, hi - purge)
        m = mask.iloc[lo:hi]
        if int(m.sum()) < min_count:
            continue
        sub = labels.iloc[lo:hi][m]
        nets.append(float((sub == 1).mean() - (sub == -1).mean()))
    if len(nets) < 3:
        return {"wf_pass": False, "consistency": 0.0, "mean_net": 0.0}
    mean_net = sum(nets) / len(nets)
    pos = mean_net > 0
    same = [x for x in nets if (x > 0) == pos and abs(x) >= edge_min]
    consistency = len(same) / len(nets)
    return {"wf_pass": consistency >= 0.6 and abs(mean_net) >= edge_min,
            "consistency": round(consistency, 2), "mean_net": round(mean_net, 3)}


def run_combo_discovery(df: pd.DataFrame, split: float = 0.7, sizes=(2, 3),
                        min_count: int = 300, oos_min_count: int = 100,
                        edge_min: float = 0.05, horizon: int = 12,
                        k_atr: float = 1.5, purge: int = None,
                        mt_alpha: float = 0.05) -> pd.DataFrame:
    """Test 2-3 condition combinations (AND). For each combo with enough samples,
    measure net edge on in-sample and on held-out (OOS) data. 'holds' = a meaningful
    edge of the same sign in BOTH samples -- the overfitting guard, doubly important
    here because we test hundreds of combos.
    RIGOR: in-sample tail is PURGED of the label horizon (no leakage into OOS) and
    'holds' additionally requires a Bonferroni-corrected z-score across ALL combos
    actually tested — with hundreds of combos, luck alone passes a fixed threshold."""
    purge = horizon if purge is None else purge
    feats = build_features(df)
    labels = triple_barrier_labels(df, horizon=horizon, k_atr=k_atr)

    n = len(df)
    k = int(n * split)
    in_f, in_l = feats.iloc[:max(0, k - purge)], labels.iloc[:max(0, k - purge)]
    out_hi = max(k, n - purge)
    out_f, out_l = feats.iloc[k:out_hi], labels.iloc[k:out_hi]
    cols = list(feats.columns)

    rows = []
    for size in sizes:
        for combo in combinations(cols, size):
            cl = list(combo)
            m_in = in_f[cl].all(axis=1)
            c_in = int(m_in.sum())
            if c_in < min_count:
                continue
            m_out = out_f[cl].all(axis=1)
            c_out = int(m_out.sum())
            si = in_l[m_in]
            p_up_in = float((si == 1).mean())
            p_dn_in = float((si == -1).mean())
            net_in = p_up_in - p_dn_in
            if c_out >= oos_min_count:
                so = out_l[m_out]
                net_out = float((so == 1).mean() - (so == -1).mean())
            else:
                net_out = float("nan")
            holds = (not np.isnan(net_out) and np.sign(net_out) == np.sign(net_in)
                     and abs(net_in) >= edge_min and abs(net_out) >= edge_min)
            rows.append({
                "conditions": " & ".join(combo),
                "size": size,
                "count_is": c_in,
                "count_oos": c_out,
                "net_is": round(net_in, 3),
                "net_oos": round(net_out, 3) if not np.isnan(net_out) else float("nan"),
                "bias": "UP" if net_in > 0 else "DOWN",
                "_z": _net_z(p_up_in, p_dn_in, c_in),
                "holds": holds,
            })
    # multiple-testing gate: Bonferroni across every combo that reached evaluation
    z_thr = _z_threshold(mt_alpha / max(1, len(rows)))
    for r in rows:
        z = r.pop("_z")
        r["z_is"] = round(z, 2) if z != float("inf") else z
        r["holds"] = bool(r["holds"] and z >= z_thr)
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.sort_values("net_oos", key=lambda s: s.abs(),
                              ascending=False, na_position="last").reset_index(drop=True)
    return res
