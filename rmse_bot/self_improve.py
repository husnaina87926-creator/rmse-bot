"""Self-improvement loop wired to the 3-account bot (SAFE).

Weekly: discover a robust NEW candidate edge per instrument (gold/BTC/ETH). Each
candidate runs in a CHALLENGER account (champion rules + candidate) alongside the
champion, forward-testing on live data. A candidate is PROMOTED into the live rules
only after it beats its champion over enough FORWARD trades — so overfit candidates
(which look great on backtest but fail forward) never get promoted. Live rules live in
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


def top_candidate(symbol: str, df, cfg: dict, current_rules: list, min_count: int = 80) -> dict:
    """Best robust NEW strategy (positive, distinct entry from current rules) or None."""
    cur = {frozenset(r["when"]) for r in current_rules}
    for s in generate_strategies(df, cfg, symbol, max_entries=8, min_count=min_count):
        if s["return"] > 0 and frozenset(s["entry"]) not in cur:
            rule = {"direction": s["direction"], "when": s["entry"]}
            if symbol != "XAUUSD":           # crypto rules are regime-specific
                rule["regime"] = "down" if s["direction"] == "sell" else "up"
            return {"rule": rule, "score": s["score"], "return": s["return"], "pf": s["pf"]}
    return None


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

def _jload(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _jsave(obj, path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)


def promotion_demotion_pass(cfg, state_dir: str, name_map: dict, start_bal: float,
                            min_trades: int = 30):
    """One safe learning heartbeat: PROMOTE forward-proven candidates, DEMOTE decayed
    promotions. Cheap (reads state files only) — can run every few minutes."""
    import datetime as _dt
    from rmse_bot.paper_trader import load_state
    live = load_live_rules(os.path.join(state_dir, "live_rules.json"))
    cands = _jload(os.path.join(state_dir, "candidates.json"), {})
    promos = _jload(os.path.join(state_dir, "promotions.json"), {})
    promoted, demoted = [], []
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # --- demotion first (un-learn decayed edges) ---
    for sym in list(promos.keys()):
        nm = name_map.get(sym)
        if nm is None:
            continue
        champ = load_state(os.path.join(state_dir, f"{nm}.json"), start_bal)
        if should_demote(champ, promos[sym].get("promoted_at", "")):
            rule = promos[sym].get("rule")
            if sym in live and rule in live[sym]:
                live[sym] = [r for r in live[sym] if r != rule]
                if not live[sym]:
                    live.pop(sym)
            demoted.append((sym, rule))
            promos.pop(sym)

    # --- promotion (forward-proven, statistically meaningful) ---
    for sym in list(cands.keys()):
        nm = name_map.get(sym)
        if nm is None:
            continue
        chal_path = os.path.join(state_dir, f"{nm}_chal.json")
        if not os.path.exists(chal_path):
            continue
        champ = load_state(os.path.join(state_dir, f"{nm}.json"), start_bal)
        chal = load_state(chal_path, start_bal)
        if should_promote(champ, chal, start_bal, min_trades):
            rule = cands[sym]["rule"]
            live[sym] = rules_for(sym, cfg, live) + [rule]
            promos[sym] = {"rule": rule, "promoted_at": now_iso}
            promoted.append((sym, rule))
            cands.pop(sym, None)
            os.remove(chal_path)              # fresh candidate gets a clean challenger

    save_live_rules(live, os.path.join(state_dir, "live_rules.json"))
    _jsave(cands, os.path.join(state_dir, "candidates.json"))
    _jsave(promos, os.path.join(state_dir, "promotions.json"))
    return promoted, demoted


def discovery_pass(cfg, state_dir: str, name_map: dict, start_bal: float,
                   fetch_fn, symbols: list):
    """Refresh candidates per symbol WITH stickiness: a candidate keeps its challenger
    until it has had a fair forward trial (30 trades) or grows stale — so a frequent
    (live) brain never resets challengers before they can prove themselves."""
    import datetime as _dt
    from rmse_bot.paper_trader import load_state
    live = load_live_rules(os.path.join(state_dir, "live_rules.json"))
    cands = _jload(os.path.join(state_dir, "candidates.json"), {})
    log = []
    for sym in symbols:
        nm = name_map.get(sym)
        try:
            existing = cands.get(sym)
            chal_path = os.path.join(state_dir, f"{nm}_chal.json")
            chal = load_state(chal_path, start_bal) if os.path.exists(chal_path) else {"closed": []}
            if keep_candidate(existing, chal):
                log.append(f"{sym}: keeping candidate (forward trial in progress, "
                           f"{len(chal.get('closed', []))} trades)")
                continue
            df = fetch_fn(sym)
            if df is None:
                log.append(f"{sym}: no data")
                continue
            cur = rules_for(sym, cfg, live)
            cand = top_candidate(sym, df, cfg, cur)
            if cand:
                if existing is None or existing.get("rule") != cand["rule"]:
                    if os.path.exists(chal_path):
                        os.remove(chal_path)
                    cand["born"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
                    cands[sym] = cand
                    log.append(f"{sym}: NEW candidate {cand['rule']['direction']} "
                               f"{' & '.join(cand['rule']['when'])} (PF {cand['pf']})")
                else:
                    cands[sym]["score"] = cand["score"]
                    log.append(f"{sym}: candidate unchanged")
            else:
                log.append(f"{sym}: no robust candidate")
        except Exception as e:
            log.append(f"{sym}: ERROR {e}")
    _jsave(cands, os.path.join(state_dir, "candidates.json"))
    return log
