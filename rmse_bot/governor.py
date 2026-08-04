"""P3 — portfolio risk governor (crypto). The admitted missing piece: the alts are correlated
(~0.27 avg pairwise), so many same-direction signals cluster and up to a dozen positions can open at
once — the real portfolio risk is far higher than any single account's 10%.

Two levers, deliberately staged:
  * CAP (enforced): at most `max_concurrent_same_dir` open crypto positions in one direction across all
    champion accounts. Beyond it, the newest signal is skipped and journalled `governor_skipped` so the
    cap's cost is MEASURED on real data, not assumed.
  * CORRELATION-AWARE SIZING (DARK / measure-only): log the sqrt(1/k) size the governor WOULD use with k
    open correlated same-direction positions. No live sizing change until the boss promotes it out of dark.

Pure functions (no I/O) so the runner stays testable; the runner supplies the cross-account view.
"""
from __future__ import annotations

import math

CRYPTO_SUFFIX = "USDT"


def _cfg(cfg: dict) -> dict:
    return cfg.get("governor", {}) or {}


def enabled(cfg: dict) -> bool:
    return bool(_cfg(cfg).get("enabled"))


def count_same_dir(open_by_account: dict, direction: str, crypto_only: bool = True) -> int:
    """Open positions in `direction` across all accounts (champions view supplied by the runner)."""
    n = 0
    for positions in open_by_account.values():
        for p in (positions or []):
            if p.get("direction") != direction:
                continue
            if crypto_only and not str(p.get("symbol", "")).endswith(CRYPTO_SUFFIX):
                continue
            n += 1
    return n


def cap_allows(cfg: dict, current_same_dir: int) -> bool:
    """True if one more same-direction crypto position is within the concurrent cap."""
    g = _cfg(cfg)
    if not g.get("enabled"):
        return True
    return current_same_dir < int(g.get("max_concurrent_same_dir", 5))


def dark_size_factor(cfg: dict, k_open_same_dir: int) -> float:
    """sqrt(1/k) correlation-aware factor the governor WOULD apply with k already-open correlated
    same-direction positions (k counts the new one). MEASURE-ONLY while corr_sizing_dark is true."""
    k = max(1, int(k_open_same_dir))
    return round(math.sqrt(1.0 / k), 3)


def sizing_is_dark(cfg: dict) -> bool:
    return bool(_cfg(cfg).get("corr_sizing_dark", True))


def _pos_key(p):
    return (p.get("symbol"), str(p.get("open_time")))


def new_positions(before_open: list, after_open: list) -> list:
    """Positions present after a step that were not open before it."""
    b = {_pos_key(p) for p in before_open}
    return [p for p in after_open if _pos_key(p) not in b]


def portfolio_open(cfg: dict, state_dir: str, self_name: str, self_open: list) -> dict:
    """Open positions across all crypto CHAMPION accounts — self from memory (post-step), others from
    disk (their most recent saved state). This is the cross-account view the cap needs."""
    import json
    import os
    out = {self_name: self_open}
    for sym in (cfg.get("crypto_rules", {}) or {}).get("symbols", []):
        nm = sym[:-4].lower()
        if nm == self_name:
            continue
        try:
            out[nm] = json.load(open(os.path.join(state_dir, f"{nm}.json"))).get("open", [])
        except Exception:
            out[nm] = []
    return out


def enforce_after_step(cfg: dict, state_dir: str, name: str, state: dict,
                       before_open: list, journal_fn=None) -> None:
    """After a crypto champion step: enforce the concurrent same-direction cap across the portfolio.
    A new position beyond the cap is REVERTED (removed before save — no cost realised, paper) and
    journalled `governor_skipped`; within the cap, the sqrt(1/k) size the governor WOULD use is
    journalled `governor_dark_size` (DARK — live sizing is NOT changed)."""
    if not enabled(cfg):
        return
    for pos in new_positions(before_open, state.get("open", [])):
        if not str(pos.get("symbol", "")).endswith(CRYPTO_SUFFIX):
            continue
        direction = pos.get("direction")
        port = portfolio_open(cfg, state_dir, name, state.get("open", []))
        existing = count_same_dir(port, direction) - 1        # same-dir open BEFORE this new entry
        cap = int(_cfg(cfg).get("max_concurrent_same_dir", 5))
        if not cap_allows(cfg, existing):
            state["open"] = [p for p in state["open"] if _pos_key(p) != _pos_key(pos)]
            if journal_fn:
                journal_fn({"type": "governor_skipped", "account": name, "symbol": pos.get("symbol"),
                            "direction": direction, "open_same_dir": existing, "cap": cap,
                            "holders": [n for n, ps in port.items() if n != name
                                        and any(q.get("direction") == direction
                                                and str(q.get("symbol", "")).endswith(CRYPTO_SUFFIX) for q in ps)]})
        elif journal_fn and sizing_is_dark(cfg):
            k = existing + 1
            journal_fn({"type": "governor_dark_size", "account": name, "symbol": pos.get("symbol"),
                        "direction": direction, "k_correlated": k, "would_size_factor": dark_size_factor(cfg, k)})


def day_loss_pct(open_by_account: dict, closed_today_pnl: float, total_start: float) -> float:
    """Portfolio day P&L as a percent of total starting capital (negative = loss)."""
    if total_start <= 0:
        return 0.0
    return 100.0 * closed_today_pnl / total_start


def day_loss_flagged(cfg: dict, day_pct: float) -> bool:
    """Phase-2 readiness flag only — INERT on paper (never blocks). True if the portfolio day loss
    exceeds the configured threshold."""
    g = _cfg(cfg)
    thr = g.get("day_loss_flag_pct")
    return thr is not None and day_pct <= -abs(float(thr))
