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
