"""W1 — EXIT-CHALLENGERS with a PAIRED promote gate.

Unlike entry-challengers (a new ENTRY rule, judged on their own ≥30-trade record), an exit-challenger
shares the champion's ENTRY exactly and only varies the EXIT. Because the entries are identical, the two
accounts open on the same candles, so we judge the PAIRED per-trade R difference (challenger − champion),
pooled across the configured coins per exit type — a far tighter test than comparing two independent
balances.

PRE-REGISTERED PAIRED PROMOTE GATE (exit-challengers only):
    PROMOTE  when  n_paired >= 15  AND  paired t-stat >= 2.0  AND  the mean R difference is positive in
             BOTH time-halves of the paired sample.
    RETIRE   mirror-wise (t-stat <= -2.0 AND negative in both halves).
    HOLD     otherwise (keep forward-testing).
Entry-rule challengers keep the old independent ≥30-trade t-stat gate; this paired gate applies ONLY
where entries are shared. risk%, the regime filter, and graduation thresholds are untouched.
"""
from __future__ import annotations

import math

MIN_PAIRED = 15
T_STAT = 2.0


def specs_for(cfg: dict, sym: str) -> list:
    """[(label, exit_overrides, account_suffix)] exit-challengers configured for this symbol."""
    ec = cfg.get("exit_challengers", {}) or {}
    if not ec.get("enabled") or sym not in ec.get("coins", []):
        return []
    return [(label, dict(ov), f"exit_{label.replace('.', '_')}")
            for label, ov in (ec.get("variants", {}) or {}).items()]


def all_specs(cfg: dict) -> list:
    """[(coin_sym, name, label, overrides, account_name)] across every configured coin."""
    ec = cfg.get("exit_challengers", {}) or {}
    out = []
    if not ec.get("enabled"):
        return out
    for sym in ec.get("coins", []):
        name = sym[:-4].lower()
        for label, ov, suffix in specs_for(cfg, sym):
            out.append((sym, name, label, ov, f"{name}_{suffix}"))
    return out


def trade_R(t: dict, risk_pct: float):
    """Per-trade R = pnl / intended-risk, where intended-risk = risk_pct% of balance BEFORE the trade
    (balance_before = balance_after - pnl). Comparable across champion and exit-challenger (same risk%)."""
    pnl = t.get("pnl", 0.0) or 0.0
    ba = t.get("balance_after")
    if ba is None:
        return None
    risk = (risk_pct / 100.0) * (ba - pnl)
    return (pnl / risk) if risk > 0 else None


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def paired_diffs(champ_closed: list, chal_closed: list, risk_pct: float) -> list:
    """R differences (challenger − champion) for trades sharing the same entry event (open_time)."""
    cm = {}
    for t in champ_closed:
        cm.setdefault(str(t.get("open_time"))[:16], t)
    diffs = []
    for t in chal_closed:
        c = cm.get(str(t.get("open_time"))[:16])
        if c is None:
            continue
        rc, rh = trade_R(c, risk_pct), trade_R(t, risk_pct)
        if rc is not None and rh is not None:
            diffs.append(rh - rc)
    return diffs


def paired_verdict(diffs: list, min_paired: int = MIN_PAIRED, t_stat: float = T_STAT) -> dict:
    """Evaluate the pre-registered paired gate over the R-difference list (time-ordered)."""
    n = len(diffs)
    res = {"n": n, "mean": round(_mean(diffs), 4), "t": 0.0,
           "both_halves": None, "verdict": "hold"}
    if n < min_paired:
        return res
    m = _mean(diffs)
    var = sum((d - m) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    t = (m / (sd / math.sqrt(n))) if sd > 0 else (math.inf if m > 0 else (-math.inf if m < 0 else 0.0))
    h = n // 2
    h1, h2 = _mean(diffs[:h]), _mean(diffs[h:])
    res["t"] = round(t, 3)
    if m > 0 and t >= t_stat and h1 > 0 and h2 > 0:
        res["verdict"], res["both_halves"] = "promote", True
    elif m < 0 and t <= -t_stat and h1 < 0 and h2 < 0:
        res["verdict"], res["both_halves"] = "retire", True
    else:
        res["both_halves"] = (h1 > 0 and h2 > 0)
    return res


def apply_live_exit(params: dict, coin_name: str, state_dir: str) -> dict:
    """Overlay any PROMOTED exit for this coin (state/live_exits.json) onto its champion params. Until a
    challenger passes the paired gate this is a no-op, so the champion exit is unchanged."""
    import json
    import os
    try:
        le = json.load(open(os.path.join(state_dir, "live_exits.json")))
        ov = le.get(coin_name)
        if ov:
            return {**params, **ov}
    except Exception:
        pass
    return params


def exit_challenger_pass(state_dir: str, cfg: dict, risk_pct: float, journal_fn=None) -> dict:
    """Read each coin's champion + exit-challenger closed trades, apply the pooled paired gate, journal
    the verdict, and on a PROMOTE write the winning exit into live_exits.json for the promoted coins.
    Called by the brain; safe to run every pass (idempotent — re-promoting the same exit is a no-op)."""
    import json
    import os

    def _closed(name):
        try:
            return json.load(open(os.path.join(state_dir, f"{name}.json"))).get("closed", [])
        except Exception:
            return []
    ec = cfg.get("exit_challengers", {}) or {}
    if not ec.get("enabled"):
        return {}
    closed_by = {}
    for sym in ec.get("coins", []):
        name = sym[:-4].lower()
        closed_by[name] = _closed(name)
        for _l, _o, suf in specs_for(cfg, sym):
            closed_by[f"{name}_{suf}"] = _closed(f"{name}_{suf}")
    verdicts = pooled_verdict(cfg, closed_by, risk_pct)
    for label, v in verdicts.items():
        if journal_fn:
            journal_fn({"type": "exit_challenger_gate", "exit": label, **v})
        if v["verdict"] == "promote":
            ov = (ec.get("variants", {}) or {}).get(label, {})
            path = os.path.join(state_dir, "live_exits.json")
            try:
                le = json.load(open(path))
            except Exception:
                le = {}
            for sym in ec.get("coins", []):
                le[sym[:-4].lower()] = dict(ov)
            from rmse_bot.atomic import atomic_json_dump
            atomic_json_dump(le, path)
            if journal_fn:
                journal_fn({"type": "exit_promoted", "exit": label, "coins": ec.get("coins", []),
                            "n": v["n"], "t": v["t"]})
    return verdicts


def pooled_verdict(cfg: dict, closed_by_account: dict, risk_pct: float) -> dict:
    """Per exit-type, pool the paired R-differences across all configured coins and apply the gate.
    `closed_by_account[name]` = that account's closed-trade list (champion + `{name}_exit_*`)."""
    ec = cfg.get("exit_challengers", {}) or {}
    gate = ec.get("gate", {}) or {}
    mn, ts = int(gate.get("min_paired", MIN_PAIRED)), float(gate.get("t_stat", T_STAT))
    out = {}
    for label, _ov, suffix in [(l, o, s) for sym in ec.get("coins", []) for (l, o, s) in specs_for(cfg, sym)]:
        pooled = []
        for sym in ec.get("coins", []):
            name = sym[:-4].lower()
            champ = closed_by_account.get(name, [])
            chal = closed_by_account.get(f"{name}_{suffix}", [])
            pooled += paired_diffs(champ, chal, risk_pct)
        out[label] = paired_verdict(pooled, mn, ts)
    return out
