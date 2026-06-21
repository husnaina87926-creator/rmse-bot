"""Virtual (paper) trader — forward-tests strategies on live data with virtual money.

Models real costs (spread + slippage + commission + swap) and leverage/margin. State
persists to JSON so each account survives restarts. Supports MULTIPLE independent
accounts (gold, BTC, ETH), each with its own balance, exit config, risk %, leverage,
and regime-specific rules (e.g. short only in down-regime, long only in up-regime).

`params` carries the per-account knobs; when omitted it falls back to the gold config,
keeping older callers/tests working. Pure w.r.t. inputs (no network) so it is testable.
"""
import json
import os
import pandas as pd

from rmse_bot.risk import position_size, trade_cost


def new_state(starting_balance: float) -> dict:
    return {"balance": float(starting_balance), "open": [], "closed": [], "history": []}


def load_state(path: str, starting_balance: float) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return new_state(starting_balance)


def save_state(state: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def default_params(cfg: dict) -> dict:
    """Per-account knobs derived from the (gold) config — the back-compat default."""
    s, e = cfg.get("strategy", {}), cfg.get("exits", {})
    r, a = cfg.get("risk", {}), cfg.get("account", {})
    return {
        "sl_atr": s.get("sl_atr", 1.5), "rr": s.get("rr", 1.5),
        "max_hold": s.get("max_hold", 12), "be_atr": e.get("breakeven_atr", 0.0),
        "trail_atr": e.get("trail_atr", 0.0), "risk_pct": a.get("risk_per_trade_pct", 1.0),
        "leverage": a.get("leverage", 500), "atr_period": r.get("atr_period", 14),
        "max_open_trades": r.get("max_open_trades", 999),
        "max_trades_per_day": r.get("max_trades_per_day", 999),
        "max_daily_loss_pct": r.get("max_daily_loss_pct", 100.0),
        "size_usd": a.get("size_usd", 100),
    }


def _swap(pos: dict, close_time: str, instr: dict) -> float:
    days = (pd.to_datetime(close_time).normalize() -
            pd.to_datetime(pos["open_time"]).normalize()).days
    return max(days, 0) * instr.get("swap_per_lot", 0.0) * pos["lots"]


def _close(state: dict, pos: dict, exit_price: float, outcome: str,
           close_time: str, cfg: dict) -> None:
    instr = cfg["instruments"][pos["symbol"]]
    move = (exit_price - pos["entry"]) if pos["direction"] == "buy" else (pos["entry"] - exit_price)
    gross = move * instr["contract_size"] * pos["lots"]
    pnl = gross - pos["cost"] - _swap(pos, close_time, instr)
    state["balance"] += pnl
    state["closed"].append({
        "symbol": pos["symbol"], "direction": pos["direction"],
        "entry": pos["entry"], "exit": round(exit_price, 5), "outcome": outcome,
        "lots": pos["lots"], "pnl": round(pnl, 2),
        "open_time": pos["open_time"], "close_time": close_time,
        "balance_after": round(state["balance"], 2),
    })


def manage_open_positions(state: dict, data_by_symbol: dict, cfg: dict, params: dict = None) -> None:
    p = params or default_params(cfg)
    max_hold, be_atr, trail_atr = p["max_hold"], p["be_atr"], p["trail_atr"]
    still_open = []
    for pos in state["open"]:
        df = data_by_symbol.get(pos["symbol"])
        closed = False
        if df is not None and not df.empty:
            fut = df[pd.to_datetime(df["time"]) > pd.to_datetime(pos["open_time"])]
            entry, tp = pos["entry"], pos["tp"]
            atr_val = pos.get("atr", 0.0)
            cur_sl, best, moved_be = pos["sl"], entry, False
            for cnt, (_, bar) in enumerate(fut.iterrows(), start=1):
                high, low = bar["high"], bar["low"]
                hit, price = None, None
                if pos["direction"] == "buy":
                    if low <= cur_sl:
                        hit, price = ("win" if cur_sl > entry else "loss"), cur_sl
                    elif high >= tp:
                        hit, price = "tp", tp
                    else:
                        best = max(best, high)
                        if be_atr and atr_val > 0 and not moved_be and best >= entry + be_atr * atr_val:
                            cur_sl, moved_be = max(cur_sl, entry), True
                        if trail_atr and atr_val > 0:
                            cur_sl = max(cur_sl, best - trail_atr * atr_val)
                else:
                    if high >= cur_sl:
                        hit, price = ("win" if cur_sl < entry else "loss"), cur_sl
                    elif low <= tp:
                        hit, price = "tp", tp
                    else:
                        best = min(best, low)
                        if be_atr and atr_val > 0 and not moved_be and best <= entry - be_atr * atr_val:
                            cur_sl, moved_be = min(cur_sl, entry), True
                        if trail_atr and atr_val > 0:
                            cur_sl = min(cur_sl, best + trail_atr * atr_val)
                if hit is None and cnt >= max_hold:
                    hit, price = "time", float(bar["close"])
                if hit:
                    _close(state, pos, price, hit, str(bar["time"]), cfg)
                    closed = True
                    break
        if not closed:
            still_open.append(pos)
    state["open"] = still_open


def scan_for_entries(state: dict, data_by_symbol: dict, cfg: dict, rules_by_symbol: dict,
                     params: dict = None, regime_state_by_symbol: dict = None,
                     news_blocked: bool = False, regime_by_symbol: dict = None) -> None:
    if news_blocked:
        return
    from rmse_bot.discovery import build_features
    from rmse_bot.indicators import atr
    from datetime import datetime, timezone

    p = params or default_params(cfg)
    max_open = p["max_open_trades"]
    open_syms = {pos["symbol"] for pos in state["open"]}
    used_margin = sum(pos.get("margin", 0.0) for pos in state["open"])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_pnl = sum(t["pnl"] for t in state["closed"]
                    if str(t.get("close_time", ""))[:10] == today)
    if today_pnl <= -abs(p["max_daily_loss_pct"]) / 100.0 * p["size_usd"]:
        return
    opened_today = (sum(1 for t in state["closed"] if str(t.get("open_time", ""))[:10] == today)
                    + sum(1 for pos in state["open"] if str(pos.get("open_time", ""))[:10] == today))
    if opened_today >= p["max_trades_per_day"]:
        return

    for sym, rules in rules_by_symbol.items():
        if sym in open_syms or len(state["open"]) >= max_open:
            continue
        if regime_by_symbol is not None and not regime_by_symbol.get(sym, True):
            continue
        df = data_by_symbol.get(sym)
        if df is None or len(df) < 250:
            continue
        feats = build_features(df)
        a = atr(df, p["atr_period"])
        row = feats.iloc[-1]
        sym_regime = (regime_state_by_symbol or {}).get(sym)

        def ok(r):
            if r.get("regime") and r["regime"] != sym_regime:   # regime-specific rule
                return False
            return all(bool(row[c]) for c in r["when"])

        matched = next((r for r in rules if ok(r)), None)
        if matched is None:
            continue
        ai = float(a.iloc[-1])
        if ai != ai or ai == 0:
            continue
        entry = float(df["close"].iloc[-1])
        d = matched["direction"]
        if d == "buy":
            sl, tp = entry - p["sl_atr"] * ai, entry + p["rr"] * p["sl_atr"] * ai
        else:
            sl, tp = entry + p["sl_atr"] * ai, entry - p["rr"] * p["sl_atr"] * ai
        instr = cfg["instruments"][sym]
        lots = position_size(state["balance"], p["risk_pct"], entry, sl, instr["contract_size"])
        margin = (lots * instr["contract_size"] * entry) / p["leverage"]
        if margin > state["balance"] - used_margin:
            continue
        used_margin += margin
        state["open"].append({
            "symbol": sym, "direction": d, "entry": entry, "sl": sl, "tp": tp,
            "lots": lots, "open_time": str(df["time"].iloc[-1]),
            "cost": trade_cost(lots, instr), "margin": margin, "atr": ai,
        })


def step(state: dict, data_by_symbol: dict, cfg: dict, rules_by_symbol: dict, now,
         params: dict = None, regime_state_by_symbol: dict = None,
         news_blocked: bool = False, regime_by_symbol: dict = None) -> dict:
    manage_open_positions(state, data_by_symbol, cfg, params)
    scan_for_entries(state, data_by_symbol, cfg, rules_by_symbol, params=params,
                     regime_state_by_symbol=regime_state_by_symbol,
                     news_blocked=news_blocked, regime_by_symbol=regime_by_symbol)
    state["history"].append({"time": str(now), "balance": round(state["balance"], 2),
                             "open_positions": len(state["open"])})
    return state
