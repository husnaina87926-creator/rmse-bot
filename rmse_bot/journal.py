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
        out["base_cum_R"] = round(sum(base), 2) if base else None
        for nm in sorted(names):
            rs = [e["variants"][nm]["R"] for e in events
                  if nm in (e.get("variants") or {})]
            if len(rs) >= 1:
                out["variants"][nm] = {
                    "n": len(rs),
                    "avg_R": round(sum(rs) / len(rs), 3),
                    "cum_R": round(sum(rs), 2),      # SHADOW-EXIT equity in R units
                    "edge_vs_base_R": (round(sum(rs) / len(rs) - out["base_avg_R"], 3)
                                       if out.get("base_avg_R") is not None else None),
                    "significant": len(rs) >= min_n,
                }
    out["_ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
    with open(os.path.join(state_dir, "lessons.json"), "w") as f:
        json.dump(out, f, indent=2)
    return out


# ---------------- per-regime rule ledger (which rule earns in which weather) ----------------

def regime_ledger(state_dir: str, names: list) -> dict:
    """PER-REGIME RULE LEDGER (observer): aggregate every account's closed trades by
    (rule fired, regime at open) -> trades / net / win rate. The bot's own record of
    WHICH rule earns in WHICH market weather. Written to state/regime_ledger.json.
    Trades from before rule-tagging (pre journal era) land in 'untagged'."""
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
        acct = {}
        for t in s.get("closed", []):
            rule = t.get("rule")
            if rule:
                rk = f"{rule.get('direction')} {'&'.join(rule.get('when', []))}"
                if rule.get("regime"):
                    rk += f" [{rule['regime']}]"
            else:
                rk = "untagged"
            reg = t.get("regime_at_open") or "none"
            b = acct.setdefault(rk, {}).setdefault(reg, {"n": 0, "net": 0.0, "wins": 0})
            b["n"] += 1
            b["net"] = round(b["net"] + float(t.get("pnl", 0.0)), 2)
            b["wins"] += 1 if t.get("pnl", 0.0) > 0 else 0
        if acct:
            for rk in acct:
                for reg, b in acct[rk].items():
                    b["win"] = round(b.pop("wins") / b["n"], 2)
            out[nm] = acct
    out["_ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
    with open(os.path.join(state_dir, "regime_ledger.json"), "w") as f:
        json.dump(out, f, indent=2)
    return out


def ledger_warnings(ledger: dict, min_n: int = 10) -> list:
    """Actionable reads from the regime ledger: rules that LOSE with a real sample in
    some regime ('this rule is not for this weather'). Info-only."""
    warns = []
    for nm, acct in ledger.items():
        if nm.startswith("_"):
            continue
        for rk, regs in acct.items():
            for reg, b in regs.items():
                if b["n"] >= min_n and b["net"] < 0:
                    warns.append(f"{nm}: '{rk}' in regime={reg} is net "
                                 f"${b['net']} over {b['n']} trades (win {b['win']:.0%})")
    return warns


# ---------------- regime-break detector (has the weather changed?) ----------------

def regime_watch_pass(state_dir: str, fetch_fn, symbols: list, name_map: dict,
                      ema_period: int = 100, rise_n: int = 20,
                      vol_pct: float = 0.99, clear_pct: float = 0.95) -> list:
    """REGIME-BREAK DETECTOR (observer, run at each 4h close): (1) track every symbol's
    daily regime and journal a 'regime_flip' event the moment it changes — including how
    many champion positions are still open from the OLD regime (caution: they were
    opened under assumptions that no longer hold); (2) journal a 'vol_break' event when
    current ATR%%-of-price enters the top (1-vol_pct) of its own history — a volatility
    regime the edge was not measured in. State in regime_watch.json; changes nothing."""
    from rmse_bot.regime import regime_state
    from rmse_bot.data_feed import resample_ohlc
    from rmse_bot.indicators import atr
    watch_path = os.path.join(state_dir, "regime_watch.json")
    watch = {}
    if os.path.exists(watch_path):
        try:
            with open(watch_path) as f:
                watch = json.load(f)
        except Exception:
            watch = {}
    log = []
    for sym in symbols:
        try:
            df = fetch_fn(sym)
            if df is None or len(df) < 300:
                continue
            daily = resample_ohlc(df, "1D")
            reg = regime_state(daily, ema_period, rise_n) or "none"
            w = watch.get(sym, {})
            old = w.get("regime")
            if old is not None and old != reg:
                nm = name_map.get(sym)
                open_old = 0
                p = os.path.join(state_dir, f"{nm}.json") if nm else None
                if p and os.path.exists(p):
                    try:
                        with open(p) as f:
                            st = json.load(f)
                        open_old = sum(1 for o in st.get("open", [])
                                       if o.get("regime_at_open") == old)
                    except Exception:
                        pass
                append_event(state_dir, {"type": "regime_flip", "symbol": sym,
                                         "from": old, "to": reg,
                                         "open_positions_from_old_regime": open_old})
                log.append(f"{sym}: REGIME FLIP {old} -> {reg}"
                           + (f" (CAUTION: {open_old} open position(s) from the old regime)"
                              if open_old else ""))
            w["regime"] = reg
            ratio = (atr(df, 14) / df["close"]).dropna()
            if len(ratio) > 300:
                cur = float(ratio.iloc[-1])
                pct = float((ratio.iloc[:-1] < cur).mean())
                if pct >= vol_pct and not w.get("vol_flag"):
                    w["vol_flag"] = True
                    append_event(state_dir, {"type": "vol_break", "symbol": sym,
                                             "atr_pct_of_price": round(cur, 5),
                                             "percentile": round(pct, 4)})
                    log.append(f"{sym}: VOL BREAK — ATR {cur:.3%} of price is at the "
                               f"{pct:.1%}ile of its own history (edge unmeasured here)")
                elif pct < clear_pct and w.get("vol_flag"):
                    w["vol_flag"] = False
                    log.append(f"{sym}: volatility back to normal ({pct:.0%}ile)")
            watch[sym] = w
        except Exception as e:
            log.append(f"{sym}: watch ERROR {e}")
    with open(watch_path, "w") as f:
        json.dump(watch, f, indent=2)
    return log


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


# ---------------- mistake taxonomy + lessons report (the trader's diary) ----------------

def mistake_taxonomy(state_dir: str) -> dict:
    """Classify every closed trade's journaled evidence into objective mistake
    categories, bucketed by month (observer — a human trader's error diary):
      exited_too_early : original TP was hit AFTER we left, or >=2 ATR left on table
      stop_too_tight   : stopped out, but the wider-SL counterfactual ended positive
      held_too_long    : time-exit at a loss (position overstayed its signal)
      regime_mismatch  : trade opened outside the rule's tagged regime (should never
                         happen — counts likely bugs, not market mistakes)
      feed_skips       : data-integrity skips (feed hygiene, not trade errors)
    Writes state/mistakes.json."""
    events = read_events(state_dir)
    key = lambda e: (e.get("account"), e.get("symbol"), str(e.get("close_time")))
    pms = {key(e): e for e in events if e.get("type") == "postmortem"}
    cfs = {key(e): e for e in events if e.get("type") == "counterfactual"}
    cats = ("exited_too_early", "stop_too_tight", "held_too_long", "regime_mismatch")
    out = {}

    def bucket(month):
        return out.setdefault(month, {c: 0 for c in cats}
                              | {"feed_skips": 0, "trades": 0,
                                 "news_window_trades": 0, "news_window_net": 0.0,
                                 "neg_sentiment_trades": 0, "neg_sentiment_net": 0.0})

    for e in events:
        if e.get("type") == "data_skip":
            bucket(str(e.get("ts", ""))[:7] or "unknown")["feed_skips"] += 1
            continue
        if e.get("type") != "close":
            continue
        b = bucket(str(e.get("close_time", ""))[:7] or "unknown")
        b["trades"] += 1
        if e.get("news_h") is not None and abs(e["news_h"]) <= 2:
            b["news_window_trades"] += 1
            b["news_window_net"] = round(b["news_window_net"] + (e.get("pnl") or 0.0), 2)
        if (e.get("llm_sentiment") or 0) <= -1:
            b["neg_sentiment_trades"] += 1
            b["neg_sentiment_net"] = round(b["neg_sentiment_net"] + (e.get("pnl") or 0.0), 2)
        pm, cf = pms.get(key(e)), cfs.get(key(e))
        if pm and (pm.get("tp_hit_after_exit")
                   or (pm.get("left_on_table_atr") or 0) >= 2):
            b["exited_too_early"] += 1
        if (e.get("outcome") == "sl" and cf
                and (cf.get("variants", {}).get("wider_sl_3.0", {}).get("R") or 0) > 0):
            b["stop_too_tight"] += 1
        if e.get("outcome") == "time" and (e.get("pnl") or 0) < 0:
            b["held_too_long"] += 1
        rule = e.get("rule") or {}
        if rule.get("regime") and e.get("regime_at_open") \
                and e["regime_at_open"] != rule["regime"]:
            b["regime_mismatch"] += 1
    res = {"months": out, "_ts": dt.datetime.now(dt.timezone.utc).isoformat()}
    with open(os.path.join(state_dir, "mistakes.json"), "w") as f:
        json.dump(res, f, indent=2)
    return res


def write_lessons_report(state_dir: str, reports_dir: str, month: str = None) -> str:
    """Auto LESSONS REPORT (the bot's monthly diary page, refreshed daily): mistakes
    by category, shadow-exit (counterfactual) standings, idea-family scoreboard,
    per-regime warnings and health flags — everything the bot 'noted' recently.
    Writes reports/lessons_<YYYY-MM>.md and returns the path."""
    month = month or f"{dt.datetime.now(dt.timezone.utc):%Y-%m}"
    mt = mistake_taxonomy(state_dir)
    mo = mt["months"].get(month, {})
    md = [f"# Lessons Report — {month}\n",
          "_Auto-written by the live brain from the trade journal. Observer-only._\n"]

    md.append(f"\n## Mistakes this month ({mo.get('trades', 0)} closed trades)\n")
    labels = {"exited_too_early": "Exited too early (TP hit after exit / >=2 ATR left)",
              "stop_too_tight": "Stop too tight (wider-SL replay ended positive)",
              "held_too_long": "Held too long (time-exit at a loss)",
              "regime_mismatch": "Regime mismatch (rule fired outside its regime!)",
              "feed_skips": "Data-feed skips (integrity guard)"}
    for k, lbl in labels.items():
        md.append(f"- {lbl}: **{mo.get(k, 0)}**\n")
    if mo.get("news_window_trades"):
        md.append(f"- Trades within ±2h of high-impact news: "
                  f"**{mo['news_window_trades']}** (net ${mo['news_window_net']})\n")
    if mo.get("neg_sentiment_trades"):
        md.append(f"- Trades closed during negative LLM news sentiment: "
                  f"**{mo['neg_sentiment_trades']}** (net ${mo['neg_sentiment_net']})\n")

    def _load(name):
        p = os.path.join(state_dir, name)
        if os.path.exists(p):
            try:
                with open(p) as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    lessons = _load("lessons.json")
    if lessons.get("variants"):
        md.append(f"\n## Shadow exits (counterfactual replays, "
                  f"{lessons.get('n_trades', 0)} trades)\n")
        md.append(f"Base exit cumulative: **{lessons.get('base_cum_R', 0)}R**\n")
        for nm, v in sorted(lessons["variants"].items(),
                            key=lambda kv: -(kv[1].get("cum_R") or 0)):
            sig = "significant" if v.get("significant") else f"n={v['n']}, not significant yet"
            md.append(f"- {nm}: cum {v.get('cum_R')}R, avg {v.get('avg_R')}R "
                      f"({v.get('edge_vs_base_R'):+}R vs base; {sig})\n")

    sb = _load("scoreboard.json")
    if sb.get("totals", {}).get("born"):
        t = sb["totals"]
        md.append(f"\n## Idea-family scoreboard\n{t['born']} candidates born — "
                  f"{t['promoted']} promoted, {t['trial_complete']} failed trial, "
                  f"{t['stale']} stale, {t['demoted']} demoted after promotion\n")
        fams = [(k, v) for k, v in sb.get("families", {}).items()
                if v.get("survival_rate") is not None]
        for k, v in sorted(fams, key=lambda kv: -(kv[1]["survival_rate"] or 0))[:8]:
            md.append(f"- {k}: survival {v['survival_rate']:.0%} "
                      f"(born {v['born']}, avg forward net {v['avg_forward_net']})\n")

    led = _load("regime_ledger.json")
    warns = ledger_warnings(led) if led else []
    if warns:
        md.append("\n## Regime warnings (rule loses in this weather)\n")
        md.extend(f"- {w}\n" for w in warns)

    health = _load("health.json")
    flags = [nm for nm, h in health.items()
             if isinstance(h, dict) and h.get("unhealthy")]
    if flags:
        md.append(f"\n## Health flags\nUnhealthy accounts (last-20 net negative): "
                  f"{', '.join(flags)}\n")

    os.makedirs(reports_dir, exist_ok=True)
    path = os.path.join(reports_dir, f"lessons_{month}.md")
    with open(path, "w") as f:
        f.write("".join(md))
    return path


# ---------------- REAL-API graduation gate (earn the right to trade real money) ----------------

GATE_CRITERIA = (
    ("forward_days", ">= 90", "3+ months of live forward history"),
    ("closed_trades", ">= 100", "enough trades to judge"),
    ("profit_factor", ">= 1.2", "live PF across champion accounts"),
    ("max_drawdown_pct", "<= 25", "combined equity drawdown"),
    ("unhealthy_champions", "== 0", "no champion currently decaying"),
    ("feed_skips_30d", "<= 5", "clean data feed"),
    ("brain_alive", "== True", "learning loop running"),
)


def graduation_gate(state_dir: str, names: list, start_bal: float, now=None) -> dict:
    """Objective checklist the bot must pass BEFORE any real Binance API is considered
    (then still testnet -> tiny size, per the plan). Computed from champion state +
    journal + health + heartbeat; writes state/graduation.json. Observer-only."""
    now = now or dt.datetime.now(dt.timezone.utc)
    trades = []
    for nm in names:
        p = os.path.join(state_dir, f"{nm}.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p) as f:
                s = json.load(f)
        except Exception:
            continue
        for t in s.get("closed", []):
            ct = t.get("close_time")
            if ct:
                trades.append((str(ct), float(t.get("pnl", 0.0))))
    trades.sort()
    pnls = [p for _, p in trades]
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    start_total = start_bal * max(1, len(names))
    equity, peak, max_dd = start_total, start_total, 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    first = pd.to_datetime(trades[0][0]) if trades else None
    if first is not None and first.tzinfo is None:
        first = first.tz_localize("UTC")

    def _load(name):
        p = os.path.join(state_dir, name)
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            return {}

    health = _load("health.json")
    unhealthy = sum(1 for nm in names
                    if isinstance(health.get(nm), dict) and health[nm].get("unhealthy"))
    cutoff = (now - dt.timedelta(days=30)).isoformat()
    skips = sum(1 for e in read_events(state_dir)
                if e.get("type") == "data_skip" and str(e.get("ts", "")) >= cutoff)
    hb = _load("brain_heartbeat.json")
    alive = False
    if hb.get("ts"):
        try:
            age = (now - dt.datetime.fromisoformat(hb["ts"])).total_seconds()
            alive = age < 3600
        except ValueError:
            pass

    values = {
        "forward_days": (now - first).days if first is not None else 0,
        "closed_trades": len(pnls),
        "profit_factor": round(wins / losses, 2) if losses > 0 else (9.99 if wins else 0.0),
        "max_drawdown_pct": round(100 * max_dd / start_total, 1),
        "unhealthy_champions": unhealthy,
        "feed_skips_30d": skips,
        "brain_alive": alive,
    }
    passed = {
        "forward_days": values["forward_days"] >= 90,
        "closed_trades": values["closed_trades"] >= 100,
        "profit_factor": values["profit_factor"] >= 1.2,
        "max_drawdown_pct": values["max_drawdown_pct"] <= 25,
        "unhealthy_champions": unhealthy == 0,
        "feed_skips_30d": skips <= 5,
        "brain_alive": alive,
    }
    out = {"criteria": [
        {"name": n, "target": tgt, "why": why,
         "value": values[n], "pass": bool(passed[n])}
        for n, tgt, why in GATE_CRITERIA],
        "passed": sum(passed.values()), "total": len(passed),
        "graduated": all(passed.values()),
        "_ts": now.isoformat()}
    with open(os.path.join(state_dir, "graduation.json"), "w") as f:
        json.dump(out, f, indent=2)
    return out
