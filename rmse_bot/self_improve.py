"""Self-improvement loop wired to the multi-account bot (SAFE).

Discover robust NEW candidate edges per instrument and run each in its own CHALLENGER
account (champion rules + candidate) alongside the champion — a TOURNAMENT of up to
TOURNAMENT_SLOTS parallel challengers per symbol, forward-testing on live data. A
candidate is PROMOTED into the live rules only after it beats its champion over enough
FORWARD trades with a statistically meaningful edge — so overfit candidates (which look
great on backtest but fail forward) never get promoted; promoted rules that decay are
DEMOTED again. Every candidate birth/retirement is journaled and aggregated by
brain_scoreboard() into which idea-families survive. Live rules live in
state/live_rules.json (mutable); the bot reads them, falling back to config.
"""
import json
import os

from rmse_bot.strategy_generator import generate_strategies


def load_live_rules(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_live_rules(rules: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(rules, f, indent=2)


def rules_for(symbol: str, cfg: dict, live: dict) -> list:
    """Current live rules for a symbol: promoted live_rules, else config default."""
    if symbol in live:
        return live[symbol]
    if symbol in cfg.get("edge_rules", {}):
        return cfg["edge_rules"][symbol]
    return cfg.get("crypto_rules", {}).get("rules", [])


def top_candidates(symbol: str, df, cfg: dict, current_rules: list, n: int = 1,
                   min_count: int = 80) -> list:
    """Up to n best robust NEW strategies (positive, entries distinct from current rules
    AND from each other) — the tournament's recruitment pool."""
    cur = {frozenset(r["when"]) for r in current_rules}
    out = []
    for s in generate_strategies(df, cfg, symbol, max_entries=8, min_count=min_count):
        if s["return"] > 0 and frozenset(s["entry"]) not in cur:
            rule = {"direction": s["direction"], "when": s["entry"]}
            if symbol != "XAUUSD":           # crypto rules are regime-specific
                rule["regime"] = "down" if s["direction"] == "sell" else "up"
            out.append({"rule": rule, "score": s["score"], "return": s["return"], "pf": s["pf"]})
            cur.add(frozenset(s["entry"]))
            if len(out) >= n:
                break
    return out


def top_candidate(symbol: str, df, cfg: dict, current_rules: list, min_count: int = 80) -> dict:
    """Best robust NEW strategy (positive, distinct entry from current rules) or None."""
    got = top_candidates(symbol, df, cfg, current_rules, 1, min_count)
    return got[0] if got else None


def should_promote(champ_state: dict, chall_state: dict, start_bal: float,
                   min_trades: int = 30, min_tstat: float = 1.5) -> bool:
    """Promote only after the challenger has enough FORWARD trades AND is profitable
    AND beats the champion's profit AND the edge is statistically meaningful (t-stat of
    per-trade pnl >= min_tstat) — a lucky streak no longer promotes. Forward proof only."""
    closed = chall_state.get("closed", [])
    if len(closed) < min_trades:
        return False
    champ_pnl = champ_state.get("balance", start_bal) - start_bal
    chall_pnl = chall_state.get("balance", start_bal) - start_bal
    if not (chall_pnl > 0 and chall_pnl > champ_pnl):
        return False
    pnls = [t.get("pnl", 0.0) for t in closed]
    n = len(pnls)
    mean = sum(pnls) / n
    var = sum((p - mean) ** 2 for p in pnls) / (n - 1) if n > 1 else 0.0
    if var <= 0:
        return mean > 0                      # zero variance: all trades identical sign
    t = mean / ((var ** 0.5) / (n ** 0.5))
    return t >= min_tstat


def should_demote(champ_state: dict, promoted_at: str,
                  min_trades: int = 20) -> bool:
    """UN-learn: a promoted rule is demoted when the champion's forward record SINCE the
    promotion has enough trades and is net NEGATIVE — the live edge decayed or was luck.
    (The bot learns AND forgets; nothing stays promoted on old glory.)"""
    since = [t for t in champ_state.get("closed", [])
             if str(t.get("close_time", "")) > str(promoted_at)]
    return len(since) >= min_trades and sum(t.get("pnl", 0.0) for t in since) < 0


def keep_candidate(existing: dict, chall_state: dict,
                   min_trades: int = 30, max_age_days: int = 45) -> bool:
    """Candidate STICKINESS (needed for a daily brain): keep testing the current
    candidate until it has had a fair forward trial — replace it only if it already
    has min_trades (and simply failed the promote gate) or it has grown stale.
    Without this, a daily brain would reset challengers before any could ever
    reach 30 forward trades, and nothing would ever promote."""
    import datetime as _dt
    if existing is None:
        return False
    n = len(chall_state.get("closed", []))
    if n >= min_trades:
        return False                          # had its trial; free to replace
    born = existing.get("born")
    if born:
        try:
            age = (_dt.datetime.now(_dt.timezone.utc)
                   - _dt.datetime.fromisoformat(born)).days
            if age > max_age_days:
                return False                  # stale: too old without enough trades
        except ValueError:
            pass
    return True


# ---------------- shared passes (used by the weekly script AND the live brain) ----------------

TOURNAMENT_SLOTS = 3        # parallel challengers per symbol


def _jload(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _jsave(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def chal_account(nm: str, slot: int) -> str:
    """Challenger account name for a tournament slot. Slot 0 keeps the historical
    '{name}_chal' name so existing state files stay valid."""
    return f"{nm}_chal" if slot == 0 else f"{nm}_chal{slot + 1}"


def candidate_list(cands: dict, symbol: str) -> list:
    """Candidates for a symbol as a list of slot-tagged dicts (tournament format).
    Backward compatible with the old single-dict format (treated as slot 0)."""
    entry = cands.get(symbol)
    if not entry:
        return []
    if isinstance(entry, dict):
        entry = [entry]
    out = []
    for i, c in enumerate(entry):
        c = dict(c)
        c.setdefault("slot", i)
        out.append(c)
    return out


def _rule_key(rule: dict):
    return (rule.get("direction"), frozenset(rule.get("when", [])), rule.get("regime"))


def promotion_demotion_pass(cfg, state_dir: str, name_map: dict, start_bal: float,
                            min_trades: int = 30):
    """One safe learning heartbeat: PROMOTE forward-proven candidates (any tournament
    slot; at most one per symbol per pass), DEMOTE decayed promotions (each promotion
    tracked separately). Cheap (reads state files only) — can run every few minutes."""
    import datetime as _dt
    from rmse_bot.paper_trader import load_state
    from rmse_bot.journal import append_event
    live = load_live_rules(os.path.join(state_dir, "live_rules.json"))
    raw = _jload(os.path.join(state_dir, "candidates.json"), {})
    cands = {sym: candidate_list(raw, sym) for sym in raw}
    promos = _jload(os.path.join(state_dir, "promotions.json"), {})
    promos = {sym: (v if isinstance(v, list) else [v]) for sym, v in promos.items()}
    promoted, demoted = [], []
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # --- demotion first (un-learn decayed edges) ---
    for sym in list(promos.keys()):
        nm = name_map.get(sym)
        if nm is None:
            continue
        champ = load_state(os.path.join(state_dir, f"{nm}.json"), start_bal)
        kept_promos = []
        for entry in promos[sym]:
            if should_demote(champ, entry.get("promoted_at", "")):
                rule = entry.get("rule")
                if sym in live and rule in live[sym]:
                    live[sym] = [r for r in live[sym] if r != rule]
                    if not live[sym]:
                        live.pop(sym)
                demoted.append((sym, rule))
                append_event(state_dir, {"type": "rule_demoted", "symbol": sym, "rule": rule,
                                         "promoted_at": entry.get("promoted_at")})
            else:
                kept_promos.append(entry)
        if kept_promos:
            promos[sym] = kept_promos
        else:
            promos.pop(sym)

    # --- promotion (forward-proven, statistically meaningful) ---
    for sym in list(cands.keys()):
        nm = name_map.get(sym)
        if nm is None:
            continue
        champ = None
        for cand in sorted(cands[sym], key=lambda c: c.get("slot", 0)):
            slot = cand.get("slot", 0)
            chal_path = os.path.join(state_dir, f"{chal_account(nm, slot)}.json")
            if not os.path.exists(chal_path):
                continue
            if champ is None:
                champ = load_state(os.path.join(state_dir, f"{nm}.json"), start_bal)
            chal = load_state(chal_path, start_bal)
            if should_promote(champ, chal, start_bal, min_trades):
                rule = cand["rule"]
                live[sym] = rules_for(sym, cfg, live) + [rule]
                promos.setdefault(sym, []).append({"rule": rule, "promoted_at": now_iso})
                promoted.append((sym, rule))
                append_event(state_dir, {
                    "type": "candidate_retired", "symbol": sym, "rule": rule, "slot": slot,
                    "reason": "promoted", "forward_trades": len(chal.get("closed", [])),
                    "forward_net": round(chal.get("balance", start_bal) - start_bal, 2)})
                cands[sym] = [c for c in cands[sym] if c is not cand]
                os.remove(chal_path)          # slot freed; next discovery recruits fresh
                break                          # at most one promotion per symbol per pass

    save_live_rules(live, os.path.join(state_dir, "live_rules.json"))
    _jsave({s: v for s, v in cands.items() if v}, os.path.join(state_dir, "candidates.json"))
    _jsave(promos, os.path.join(state_dir, "promotions.json"))
    return promoted, demoted


def discovery_pass(cfg, state_dir: str, name_map: dict, start_bal: float,
                   fetch_fn, symbols: list, n_slots: int = TOURNAMENT_SLOTS):
    """TOURNAMENT recruitment WITH stickiness: each symbol runs up to n_slots parallel
    challengers. A candidate keeps its slot until it has had a fair forward trial
    (30 trades) or grows stale; freed slots are refilled with the best distinct new
    ideas. Every birth and retirement is journaled, so the Brain Scoreboard can learn
    which idea-families keep surviving forward trials and which keep dying."""
    import datetime as _dt
    from rmse_bot.paper_trader import load_state
    from rmse_bot.journal import append_event
    live = load_live_rules(os.path.join(state_dir, "live_rules.json"))
    raw = _jload(os.path.join(state_dir, "candidates.json"), {})
    out_cands = {}
    log = []
    for sym in symbols:
        nm = name_map.get(sym)
        try:
            kept, expiring = [], []
            for cand in candidate_list(raw, sym):
                slot = cand.get("slot", 0)
                chal_path = os.path.join(state_dir, f"{chal_account(nm, slot)}.json")
                chal = load_state(chal_path, start_bal) if os.path.exists(chal_path) \
                    else {"closed": []}
                if keep_candidate(cand, chal):
                    kept.append(cand)
                    log.append(f"{sym}: slot{slot} keeping candidate (forward trial in "
                               f"progress, {len(chal.get('closed', []))} trades)")
                else:
                    expiring.append((cand, chal))
            if len(kept) >= n_slots:
                out_cands[sym] = kept
                continue
            df = fetch_fn(sym)
            if df is None:
                out_cands[sym] = kept + [c for c, _ in expiring]   # no data: change nothing
                log.append(f"{sym}: no data")
                continue
            cur = rules_for(sym, cfg, live) + [c["rule"] for c in kept]
            fresh = top_candidates(sym, df, cfg, cur, n=n_slots - len(kept))
            # an expiring candidate re-discovered as a top pick keeps running unchanged
            for nc in list(fresh):
                for pair in list(expiring):
                    if _rule_key(pair[0]["rule"]) == _rule_key(nc["rule"]):
                        pair[0]["score"] = nc["score"]
                        kept.append(pair[0])
                        expiring.remove(pair)
                        fresh.remove(nc)
                        log.append(f"{sym}: slot{pair[0].get('slot', 0)} candidate unchanged")
                        break
            # retire displaced candidates (journal the outcome for the scoreboard)
            for cand, chal in expiring:
                slot = cand.get("slot", 0)
                n = len(chal.get("closed", []))
                reason = "trial_complete" if n >= 30 else "stale"
                append_event(state_dir, {
                    "type": "candidate_retired", "symbol": sym, "rule": cand["rule"],
                    "slot": slot, "reason": reason, "forward_trades": n,
                    "forward_net": round(chal.get("balance", start_bal) - start_bal, 2)})
                p = os.path.join(state_dir, f"{chal_account(nm, slot)}.json")
                if os.path.exists(p):
                    os.remove(p)
                log.append(f"{sym}: slot{slot} RETIRED ({reason}, {n} trades)")
            # recruit new candidates into free slots
            used = {c.get("slot", 0) for c in kept}
            free = [s for s in range(n_slots) if s not in used]
            for nc in fresh:
                if not free:
                    break
                slot = free.pop(0)
                p = os.path.join(state_dir, f"{chal_account(nm, slot)}.json")
                if os.path.exists(p):
                    os.remove(p)               # fresh candidate gets a fresh account
                nc["slot"] = slot
                nc["born"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
                kept.append(nc)
                append_event(state_dir, {"type": "candidate_born", "symbol": sym,
                                         "rule": nc["rule"], "slot": slot, "pf": nc.get("pf")})
                log.append(f"{sym}: slot{slot} NEW candidate {nc['rule']['direction']} "
                           f"{' & '.join(nc['rule']['when'])} (PF {nc['pf']})")
            if free:
                log.append(f"{sym}: {len(free)} free slot(s), no further robust candidate")
            out_cands[sym] = kept
        except Exception as e:
            out_cands[sym] = candidate_list(raw, sym)              # error: change nothing
            log.append(f"{sym}: ERROR {e}")
    for sym in raw:                            # symbols not in this pass keep their entries
        if sym not in out_cands:
            out_cands[sym] = candidate_list(raw, sym)
    _jsave({s: v for s, v in out_cands.items() if v},
           os.path.join(state_dir, "candidates.json"))
    return log


# ---------------- brain scoreboard (which idea-families survive?) ----------------

def brain_scoreboard(state_dir: str) -> dict:
    """Aggregate every candidate's life (born -> promoted / trial_complete / stale) and
    every live-rule demotion into per-idea-family stats: which entry conditions,
    directions and regimes keep SURVIVING forward trials and which keep dying.
    Writes state/scoreboard.json. Observer-only — informs discovery, changes nothing."""
    import datetime as _dt
    from rmse_bot.journal import read_events

    def fam_keys(rule):
        ks = [f"cond:{c}" for c in rule.get("when", [])]
        ks.append(f"dir:{rule.get('direction')}")
        if rule.get("regime"):
            ks.append(f"regime:{rule['regime']}")
        return ks

    buckets = ("born", "promoted", "trial_complete", "stale", "demoted")
    totals = {b: 0 for b in buckets}
    fams = {}
    for e in read_events(state_dir):
        t, rule = e.get("type"), e.get("rule")
        if not rule:
            continue
        if t == "candidate_born":
            b = "born"
        elif t == "candidate_retired":
            b = e.get("reason")
        elif t == "rule_demoted":
            b = "demoted"
        else:
            continue
        if b not in totals:
            continue
        totals[b] += 1
        for k in fam_keys(rule):
            f = fams.setdefault(k, {bb: 0 for bb in buckets} | {"net_sum": 0.0, "net_n": 0})
            f[b] += 1
            if t == "candidate_retired" and e.get("forward_net") is not None:
                f["net_sum"] += float(e["forward_net"])
                f["net_n"] += 1
    for f in fams.values():
        f["avg_forward_net"] = round(f["net_sum"] / f["net_n"], 2) if f["net_n"] else None
        f.pop("net_sum"), f.pop("net_n")
        done = f["promoted"] + f["trial_complete"] + f["stale"]
        f["survival_rate"] = round(f["promoted"] / done, 3) if done else None
    out = {"totals": totals, "families": fams,
           "_ts": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    _jsave(out, os.path.join(state_dir, "scoreboard.json"))
    return out
