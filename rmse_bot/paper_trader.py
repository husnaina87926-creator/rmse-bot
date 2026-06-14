"""Virtual (paper) trader — forward-tests the strategy on live data with virtual money.

Models real costs: spread + slippage + commission (at entry) and swap (overnight),
plus leverage/margin (can't open a position you can't margin). State persists to JSON
so the trader survives restarts (it runs every 15 min on free hosting).

Designed to be driven by `step(state, data_by_symbol, cfg, rules_by_symbol, now)` where
`data_by_symbol[sym]` is a recent canonical OHLC frame. Pure w.r.t. its inputs (no
network here) so it is fully unit-testable; the runner script supplies live data.
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


def _swap(pos: dict, close_time: str, instr: dict) -> float:
    days = (pd.to_datetime(close_time).normalize() -
            pd.to_datetime(pos["open_time"]).normalize()).days
    return max(days, 0) * instr.get("swap_per_lot", 0.0) * pos["lots"]


def _close(state: dict, pos: dict, exit_price: float, outcome: str,
           close_time: str, cfg: dict) -> None:
    instr = cfg["instruments"][pos["symbol"]]
    move = (exit_price - pos["entry"]) if pos["direction"] == "buy" else (pos["entry"] - exit_price)
    gross = move * instr["contract_size"] * pos["lots"]
    swap = _swap(pos, close_time, instr)
    pnl = gross - pos["cost"] - swap
    state["balance"] += pnl
    state["closed"].append({
        "symbol": pos["symbol"], "direction": pos["direction"],
        "entry": pos["entry"], "exit": round(exit_price, 5), "outcome": outcome,
        "lots": pos["lots"], "pnl": round(pnl, 2),
        "open_time": pos["open_time"], "close_time": close_time,
        "balance_after": round(state["balance"], 2),
    })


def manage_open_positions(state: dict, data_by_symbol: dict, cfg: dict) -> None:
    max_hold = cfg["strategy"]["max_hold"]
    be_atr = cfg.get("exits", {}).get("breakeven_atr", 0.0)
    trail_atr = cfg.get("exits", {}).get("trail_atr", 0.0)
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


def scan_for_entries(state: dict, data_by_symbol: dict, cfg: dict,
                     rules_by_symbol: dict) -> None:
    from rmse_bot.discovery import build_features
    from rmse_bot.indicators import atr
    from datetime import datetime, timezone

    strat = cfg["strategy"]
    rcfg = cfg.get("risk", {})
    max_open = rcfg.get("max_open_trades", 999)
    open_syms = {p["symbol"] for p in state["open"]}
    used_margin = sum(p.get("margin", 0.0) for p in state["open"])

    # risk gate: daily loss limit (stop opening new trades after a bad day)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_pnl = sum(t["pnl"] for t in state["closed"]
                    if str(t.get("close_time", ""))[:10] == today)
    loss_cap = -abs(rcfg.get("max_daily_loss_pct", 100.0)) / 100.0 * cfg["account"]["size_usd"]
    if today_pnl <= loss_cap:
        return

    for sym, rules in rules_by_symbol.items():
        if sym in open_syms or len(state["open"]) >= max_open:
            continue
        df = data_by_symbol.get(sym)
        if df is None or len(df) < 250:
            continue
        feats = build_features(df)
        a = atr(df, cfg["risk"]["atr_period"])
        row = feats.iloc[-1]                       # latest CLOSED bar
        matched = next((r for r in rules if all(bool(row[c]) for c in r["when"])), None)
        if matched is None:
            continue
        ai = float(a.iloc[-1])
        if ai != ai or ai == 0:                    # NaN or zero ATR
            continue
        entry = float(df["close"].iloc[-1])
        d = matched["direction"]
        if d == "buy":
            sl = entry - strat["sl_atr"] * ai
            tp = entry + strat["rr"] * strat["sl_atr"] * ai
        else:
            sl = entry + strat["sl_atr"] * ai
            tp = entry - strat["rr"] * strat["sl_atr"] * ai
        instr = cfg["instruments"][sym]
        lots = position_size(state["balance"], cfg["account"]["risk_per_trade_pct"],
                             entry, sl, instr["contract_size"])
        notional = lots * instr["contract_size"] * entry
        margin = notional / cfg["account"].get("leverage", 500)
        if margin > state["balance"] - used_margin:     # not enough free margin
            continue
        used_margin += margin
        state["open"].append({
            "symbol": sym, "direction": d, "entry": entry, "sl": sl, "tp": tp,
            "lots": lots, "open_time": str(df["time"].iloc[-1]),
            "cost": trade_cost(lots, instr), "margin": margin, "atr": ai,
        })


def step(state: dict, data_by_symbol: dict, cfg: dict, rules_by_symbol: dict,
         now) -> dict:
    manage_open_positions(state, data_by_symbol, cfg)
    scan_for_entries(state, data_by_symbol, cfg, rules_by_symbol)
    state["history"].append({"time": str(now), "balance": round(state["balance"], 2),
                             "open_positions": len(state["open"])})
    return state
