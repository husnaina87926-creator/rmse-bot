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


# ---------------- counterfactual engine (learn from roads NOT taken) ----------------

DEFAULT_VARIANTS = {
    "wider_sl_3.0":  {"sl_atr": 3.0, "rr": 1.0, "max_hold": 24, "be_atr": 0.0, "trail_atr": 0.0},
    "tighter_sl_1.5": {"sl_atr": 1.5, "rr": 1.0, "max_hold": 24, "be_atr": 0.0, "trail_atr": 0.0},
    "rr_2.0":        {"sl_atr": 2.0, "rr": 2.0, "max_hold": 24, "be_atr": 0.0, "trail_atr": 0.0},
    "hold_48":       {"sl_atr": 2.0, "rr": 1.0, "max_hold": 48, "be_atr": 0.0, "trail_atr": 0.0},
    "breakeven_1.0": {"sl_atr": 2.0, "rr": 1.0, "max_hold": 24, "be_atr": 1.0, "trail_atr": 0.0},
    "trail_1.5":     {"sl_atr": 2.0, "rr": 1.0, "max_hold": 24, "be_atr": 0.0, "trail_atr": 1.5},
}


def run_counterfactuals(state_dir: str, fetch_fn, variants: dict = None,
                        max_per_run: int = 20) -> int:
    """For each closed trade, replay the SAME entry on the SAME bars under alternative
    exit configs and record what each would have produced (in R units). A human can only
    learn from the road taken; the bot learns from six roads per trade — risk-free.
    Observer-only: results are journaled ('counterfactual' events), nothing auto-changes."""
    from rmse_bot.backtest import simulate_trade_dynamic
    variants = variants or DEFAULT_VARIANTS
    events = read_events(state_dir)
    done = {(e.get("account"), e.get("symbol"), str(e.get("close_time")))
            for e in events if e.get("type") == "counterfactual"}
    todo = [e for e in events if e.get("type") == "close"
            and e.get("atr") and e.get("entry") is not None
            and (e.get("account"), e.get("symbol"), str(e.get("close_time"))) not in done]
    max_hold_needed = max(v["max_hold"] for v in variants.values())
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
            ot = pd.to_datetime(str(e.get("open_time")))
            if t.dt.tz is not None and ot.tzinfo is None:
                ot = ot.tz_localize(t.dt.tz)
            fut = df[t > ot].head(max_hold_needed)
            if len(fut) < 2:
                continue
            d, entry, atr_v = e["direction"], float(e["entry"]), float(e["atr"])
            base_sl = e.get("sl")
            base_dist = abs(entry - base_sl) if base_sl is not None else 2.0 * atr_v
            base_move = (float(e.get("exit", entry)) - entry) * (1 if d == "buy" else -1)
            results = {}
            for nm, v in variants.items():
                sd = v["sl_atr"] * atr_v
                if d == "buy":
                    sl, tp = entry - sd, entry + v["rr"] * sd
                else:
                    sl, tp = entry + sd, entry - v["rr"] * sd
                label, exit_p = simulate_trade_dynamic(
                    d, entry, sl, tp, atr_v, fut.head(v["max_hold"]),
                    be_trigger_atr=v["be_atr"], trail_atr=v["trail_atr"])
                if label == "open":               # window not finished yet -> exit at last close
                    exit_p = float(fut["close"].iloc[min(v["max_hold"], len(fut)) - 1])
                    label = "time"
                mv = (exit_p - entry) * (1 if d == "buy" else -1)
                results[nm] = {"outcome": label, "R": round(mv / sd, 3)}
            append_event(state_dir, {
                "type": "counterfactual", "account": e.get("account"), "symbol": sym,
                "close_time": str(e.get("close_time")), "base_outcome": e.get("outcome"),
                "base_R": round(base_move / base_dist, 3) if base_dist else None,
                "variants": results,
            })
            written += 1
        except Exception:
            continue
    return written


def counterfactual_summary(state_dir: str, min_n: int = 10) -> dict:
    """Aggregate lessons: per exit-variant, average R vs the base exit's average R over
    the same trades. Written to state/lessons.json — the bot's own 'what I keep leaving
    on the table' notebook. (Any promising variant must STILL pass the normal
    forward-test gate before ever touching live rules — no shortcut.)"""
    events = [e for e in read_events(state_dir) if e.get("type") == "counterfactual"]
    out = {"n_trades": len(events), "variants": {}}
    if events:
        base = [e.get("base_R") for e in events if e.get("base_R") is not None]
        out["base_avg_R"] = round(sum(base) / len(base), 3) if base else None
        names = set()
        for e in events:
            names.update((e.get("variants") or {}).keys())
        for nm in sorted(names):
            rs = [e["variants"][nm]["R"] for e in events
                  if nm in (e.get("variants") or {})]
            if len(rs) >= 1:
                out["variants"][nm] = {
                    "n": len(rs),
                    "avg_R": round(sum(rs) / len(rs), 3),
                    "edge_vs_base_R": (round(sum(rs) / len(rs) - out["base_avg_R"], 3)
                                       if out.get("base_avg_R") is not None else None),
                    "significant": len(rs) >= min_n,
                }
    out["_ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
    with open(os.path.join(state_dir, "lessons.json"), "w") as f:
        json.dump(out, f, indent=2)
    return out


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
