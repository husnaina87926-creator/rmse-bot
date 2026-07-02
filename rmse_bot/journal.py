"""Trade Journal + Health Monitor + Data Integrity Guard (Phase 1 of the god-level brain).

DESIGN RULE: everything here is an OBSERVER — it records, measures and guards, but NEVER
changes what the strategy does on good data. Accuracy can only be protected, not reduced:
  - journal: every open/close is recorded with full context (rule fired, regime, ATR,
    decision latency vs candle close) -> state/journal.jsonl (append-only, one JSON/line)
  - post-mortems: after a trade closes, record what happened NEXT (did the original TP
    get hit after we exited? how much move was left on the table?) — the human trader's
    "note everything" habit, automated
  - health: rolling per-account form (last-30 PF/win/net) + UNHEALTHY flag when the last
    20 closed trades are net negative -> state/health.json
  - integrity: refuse to act on broken data (duplicate/backwards/stale/gappy candles) —
    skipping a garbage bar protects accuracy, never hurts it
"""
import json
import os
import datetime as dt

import pandas as pd


# ---------------- journal primitives ----------------

def _journal_path(state_dir: str) -> str:
    return os.path.join(state_dir, "journal.jsonl")


def append_event(state_dir: str, event: dict) -> None:
    event = dict(event)
    event.setdefault("ts", dt.datetime.now(dt.timezone.utc).isoformat())
    os.makedirs(state_dir, exist_ok=True)
    with open(_journal_path(state_dir), "a") as f:
        f.write(json.dumps(event) + "\n")


def read_events(state_dir: str) -> list:
    p = _journal_path(state_dir)
    if not os.path.exists(p):
        return []
    out = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


# ---------------- open/close capture (called by runners around step()) ----------------

def diff_and_journal(state_dir: str, account: str, before_open: list, before_closed_n: int,
                     state: dict, bar_time, interval_s: int, now=None,
                     extra: dict = None) -> None:
    """Compare account state before/after a step() and journal any new opens/closes.
    decision_latency_s = how long after the candle CLOSE the decision was processed."""
    now = now or dt.datetime.now(dt.timezone.utc)
    latency = None
    try:
        bt = pd.to_datetime(bar_time)
        if bt.tzinfo is None:
            bt = bt.tz_localize("UTC")
        latency = round((now - bt).total_seconds() - interval_s, 1)
    except Exception:
        pass
    before_keys = {(p.get("symbol"), str(p.get("open_time"))) for p in before_open}
    for pos in state.get("open", []):
        key = (pos.get("symbol"), str(pos.get("open_time")))
        if key not in before_keys:
            append_event(state_dir, {
                "type": "open", "account": account, **{k: pos.get(k) for k in
                    ("symbol", "direction", "entry", "sl", "tp", "lots", "atr",
                     "open_time", "rule", "regime_at_open")},
                "decision_latency_s": latency, **(extra or {}),
            })
    new_closes = state.get("closed", [])[before_closed_n:]
    # to enrich closes with the original sl/tp/atr, look them up in the pre-step open list
    pre = {(p.get("symbol"), str(p.get("open_time"))): p for p in before_open}
    for tr in new_closes:
        src = pre.get((tr.get("symbol"), str(tr.get("open_time"))), {})
        append_event(state_dir, {
            "type": "close", "account": account, **tr,
            "sl": src.get("sl"), "tp": src.get("tp"), "atr": src.get("atr"),
            "rule": tr.get("rule") or src.get("rule"),
            "regime_at_open": tr.get("regime_at_open") or src.get("regime_at_open"),
            "decision_latency_s": latency, **(extra or {}),
        })


# ---------------- post-mortems (what happened AFTER we exited) ----------------

def run_postmortems(state_dir: str, fetch_fn, lookahead: int = 24, max_per_run: int = 40) -> int:
    """For each closed trade without a post-mortem yet, look at the bars AFTER the exit:
    did the original TP get hit after we left? how much favorable move (in ATR) did we
    leave on the table? Appends 'postmortem' events; returns how many were written."""
    events = read_events(state_dir)
    done = {(e.get("account"), e.get("symbol"), str(e.get("close_time")))
            for e in events if e.get("type") == "postmortem"}
    todo = [e for e in events if e.get("type") == "close"
            and (e.get("account"), e.get("symbol"), str(e.get("close_time"))) not in done]
    written = 0
    dfs = {}
    for e in todo[:max_per_run]:
        sym = e.get("symbol")
        try:
            if sym not in dfs:
                dfs[sym] = fetch_fn(sym)
            df = dfs[sym]
            if df is None or df.empty:
                continue
            t = pd.to_datetime(df["time"])
            ct = pd.to_datetime(str(e.get("close_time")))
            if t.dt.tz is not None and ct.tzinfo is None:
                ct = ct.tz_localize(t.dt.tz)
            fut = df[t > ct].head(lookahead)
            if fut.empty:
                continue                        # too fresh — postmortem next time
            d, exit_p = e.get("direction"), float(e.get("exit") or 0)
            tp, atr_v = e.get("tp"), e.get("atr") or 0
            if d == "buy":
                best = float(fut["high"].max())
                left = (best - exit_p) / atr_v if atr_v else None
                tp_after = bool(tp is not None and best >= tp)
            else:
                best = float(fut["low"].min())
                left = (exit_p - best) / atr_v if atr_v else None
                tp_after = bool(tp is not None and best <= tp)
            append_event(state_dir, {
                "type": "postmortem", "account": e.get("account"), "symbol": sym,
                "close_time": str(e.get("close_time")), "outcome": e.get("outcome"),
                "pnl": e.get("pnl"),
                "tp_hit_after_exit": tp_after,
                "left_on_table_atr": round(left, 2) if left is not None else None,
                "bars_checked": int(len(fut)),
            })
            written += 1
        except Exception:
            continue
    return written


# ---------------- champion health monitor ----------------

def health_snapshot(state_dir: str, names: list, start_bal: float,
                    window: int = 30, flag_window: int = 20) -> dict:
    """Rolling form per account: last-`window` closed trades -> net/win/pf; UNHEALTHY when
    the last `flag_window` trades are net negative. Pure read-only; writes state/health.json."""
    out = {}
    for nm in names:
        p = os.path.join(state_dir, f"{nm}.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p) as f:
                s = json.load(f)
        except Exception:
            continue
        closed = s.get("closed", [])
        last = closed[-window:]
        pnls = [t.get("pnl", 0.0) for t in last]
        wins = [x for x in pnls if x > 0]
        gl = -sum(x for x in pnls if x < 0)
        recent = [t.get("pnl", 0.0) for t in closed[-flag_window:]]
        out[nm] = {
            "balance": s.get("balance"),
            "trades_total": len(closed),
            "recent_n": len(pnls),
            "recent_net": round(sum(pnls), 2),
            "recent_win": round(len(wins) / len(pnls), 2) if pnls else None,
            "recent_pf": round(sum(wins) / gl, 2) if gl > 0 else None,
            "unhealthy": bool(len(recent) >= flag_window and sum(recent) < 0),
        }
    out["_ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
    with open(os.path.join(state_dir, "health.json"), "w") as f:
        json.dump(out, f, indent=2)
    return out


# ---------------- data integrity guard ----------------

def integrity_check(df, interval_s: int, now=None, allow_session_gaps: bool = False,
                    stale_mult: float = 3.0) -> tuple:
    """Return (ok, reason). Refuses: empty/short feeds, duplicate timestamps, backwards
    time, internal gaps (missing candles; skipped for session markets like gold where
    weekend gaps are normal), and a stale last candle (dead feed)."""
    if df is None or len(df) < 50:
        return False, "too_few_bars"
    t = pd.to_datetime(df["time"])
    if t.duplicated().any():
        return False, "duplicate_timestamps"
    diffs = t.diff().dt.total_seconds().dropna()
    if (diffs <= 0).any():
        return False, "non_monotonic_time"
    if not allow_session_gaps and (diffs > 1.5 * interval_s).any():
        return False, "gap_missing_candles"
    now = now or dt.datetime.now(dt.timezone.utc)
    last = t.iloc[-1]
    if last.tzinfo is None:
        last = last.tz_localize("UTC")
    stale_limit = (3 * 86400) if allow_session_gaps else stale_mult * interval_s
    if (now - last).total_seconds() > stale_limit + interval_s:
        return False, "stale_last_candle"
    return True, "ok"
