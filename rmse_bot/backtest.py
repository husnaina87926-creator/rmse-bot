from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from rmse_bot.signal_engine import generate_signal
from rmse_bot.risk import position_size, trade_cost


@dataclass
class BacktestResult:
    trades: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def simulate_trade(direction: str, entry: float, sl: float, tp: float,
                   future: pd.DataFrame) -> str:
    for _, bar in future.iterrows():
        if direction == "buy":
            if bar["low"] <= sl:
                return "sl"
            if bar["high"] >= tp:
                return "tp"
        else:
            if bar["high"] >= sl:
                return "sl"
            if bar["low"] <= tp:
                return "tp"
    return "open"


def simulate_trade_dynamic(direction: str, entry: float, sl: float, tp: float,
                           atr_val: float, future: pd.DataFrame,
                           be_trigger_atr: float = 0.0, trail_atr: float = 0.0):
    """Walk future bars with optional break-even and trailing stops.
    - be_trigger_atr>0: once price is +be_trigger_atr*ATR in profit, move stop to entry.
    - trail_atr>0: trail the stop trail_atr*ATR behind the best price seen.
    Exits are checked against the stop established up to the PREVIOUS bar (no intrabar
    look-ahead); the stop only ratchets after a bar survives. Returns (label, exit_price)."""
    cur_sl = sl
    best = entry
    moved_be = False
    for _, bar in future.iterrows():
        high, low = bar["high"], bar["low"]
        if direction == "buy":
            if low <= cur_sl:
                return ("win" if cur_sl > entry else "loss", cur_sl)
            if high >= tp:
                return ("tp", tp)
            best = max(best, high)
            if be_trigger_atr and not moved_be and best >= entry + be_trigger_atr * atr_val:
                cur_sl = max(cur_sl, entry)
                moved_be = True
            if trail_atr:
                cur_sl = max(cur_sl, best - trail_atr * atr_val)
        else:
            if high >= cur_sl:
                return ("win" if cur_sl < entry else "loss", cur_sl)
            if low <= tp:
                return ("tp", tp)
            best = min(best, low)
            if be_trigger_atr and not moved_be and best <= entry - be_trigger_atr * atr_val:
                cur_sl = min(cur_sl, entry)
                moved_be = True
            if trail_atr:
                cur_sl = min(cur_sl, best + trail_atr * atr_val)
    return ("time", float(future["close"].iloc[-1]))


def compute_metrics(trades: list, start_balance: float) -> dict:
    if not trades:
        return {"num_trades": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy": 0, "max_drawdown": 0, "total_return": 0}
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    gross_win, gross_loss = sum(wins), sum(losses)
    equity, peak, max_dd = start_balance, start_balance, 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "num_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
        "expectancy": sum(pnls) / len(trades),
        "max_drawdown": max_dd,
        "total_return": sum(pnls),
    }


def backtest(df_15m: pd.DataFrame, df_1h: pd.DataFrame, cfg: dict,
             instr: dict, lookback: int = 250) -> BacktestResult:
    balance = cfg["account"]["size_usd"]
    trades = []
    i = lookback
    while i < len(df_15m) - 1:
        window = df_15m.iloc[:i + 1]
        if "time" in df_1h.columns:
            h_ctx = df_1h[df_1h["time"] <= window["time"].iloc[-1]]
        else:
            h_ctx = df_1h
        if len(h_ctx) < cfg["signal"]["ema_trend"]:
            i += 1
            continue
        sig = generate_signal(h_ctx, window, cfg)
        if sig is None:
            i += 1
            continue
        future = df_15m.iloc[i + 1:i + 1 + 96]   # next ~24h of 15m bars
        outcome = simulate_trade(sig.direction, sig.entry, sig.sl, sig.tp, future)
        lots = position_size(balance, cfg["account"]["risk_per_trade_pct"],
                             sig.entry, sig.sl, instr["contract_size"])
        cost = trade_cost(lots, instr)
        if outcome == "tp":
            gross = abs(sig.tp - sig.entry) * instr["contract_size"] * lots
            pnl = gross - cost
        elif outcome == "sl":
            gross = -abs(sig.entry - sig.sl) * instr["contract_size"] * lots
            pnl = gross - cost
        else:
            i += 1
            continue
        balance += pnl
        trades.append({"time": sig.time, "dir": sig.direction,
                       "outcome": outcome, "pnl": pnl, "balance": balance,
                       "confidence": sig.confidence, "reason": sig.reason})
        i += 96   # no overlapping trades
    return BacktestResult(trades=trades,
                          metrics=compute_metrics(trades, cfg["account"]["size_usd"]))


def walk_forward(df: pd.DataFrame, cfg: dict, instr: dict, rules: list,
                 train_len: int, test_len: int, param_grid: list,
                 min_train_trades: int = 30) -> list:
    """Rolling walk-forward. For each window: tune the SL/RR/hold config on the
    train slice, then apply that config to the *following* unseen test slice.
    Test slices are non-overlapping and tile the whole timeline -> if the edge
    survives across many different periods, it is regime-robust, not a lucky fit."""
    results = []
    n = len(df)
    start = 0
    while start + train_len + test_len <= n:
        train = df.iloc[start:start + train_len].reset_index(drop=True)
        test = df.iloc[start + train_len:start + train_len + test_len].reset_index(drop=True)
        best = None
        for sl, rr, mh in param_grid:
            m = backtest_edge(train, cfg, instr, rules, sl_atr=sl, rr=rr, max_hold=mh).metrics
            # cap PF for selection: an inf PF (zero losing trades) is a degenerate lucky
            # config and must not auto-win the grid; tie-break on total return instead
            pf = min(m["profit_factor"], 10.0)
            score = (pf, m["total_return"])
            if m["num_trades"] >= min_train_trades and (best is None or score > best[0]):
                best = (score, sl, rr, mh)
        if best is not None:
            _, sl, rr, mh = best
            tm = backtest_edge(test, cfg, instr, rules, sl_atr=sl, rr=rr, max_hold=mh).metrics
            results.append({
                "train_pf": round(best[0][0], 2), "sl": sl, "rr": rr, "hold": mh,
                "test_pf": round(tm["profit_factor"], 2), "test_trades": tm["num_trades"],
                "test_win": round(tm["win_rate"], 2), "test_return": round(tm["total_return"], 2),
                "start_time": str(test["time"].iloc[0])[:10] if not test.empty else "",
            })
        start += test_len
    return results


def backtest_edge(df: pd.DataFrame, cfg: dict, instr: dict, rules: list,
                  sl_atr: float = 1.5, rr: float = 1.5, max_hold: int = 12,
                  lookback: int = 250, be_atr: float = 0.0,
                  trail_atr: float = 0.0, regime_mask=None,
                  compound: bool = True) -> BacktestResult:
    """Backtest a discovery-derived rule set. A rule = {'direction','when':[features]}.
    When all of a rule's boolean features are true on a bar, open a trade with an
    ATR-based SL/TP; exit at TP/SL or at market after `max_hold` bars (time exit).
    Features are precomputed once (O(n)). Costs/sizing reuse the shared risk module.
    compound=False sizes every trade off the STARTING balance (fixed-risk additive) —
    use for edge VALIDATION, where compounding's path-dependence would let the balance
    trajectory, not the edge, decide the result."""
    from rmse_bot.discovery import build_features
    from rmse_bot.indicators import atr

    feats = build_features(df)
    a = atr(df, cfg["risk"]["atr_period"]).values
    close = df["close"].values
    balance = cfg["account"]["size_usd"]
    trades = []
    n = len(df)
    i = lookback
    while i < n - 1:
        if regime_mask is not None and not regime_mask[i]:   # daily regime not up -> skip
            i += 1
            continue
        row = feats.iloc[i]
        matched = None
        for rule in rules:
            if all(bool(row[c]) for c in rule["when"]):
                matched = rule
                break
        if matched is None or np.isnan(a[i]) or a[i] == 0:
            i += 1
            continue
        entry = float(close[i])
        direction = matched["direction"]
        if direction == "buy":
            sl, tp = entry - sl_atr * a[i], entry + rr * sl_atr * a[i]
        else:
            sl, tp = entry + sl_atr * a[i], entry - rr * sl_atr * a[i]
        future = df.iloc[i + 1:i + 1 + max_hold]
        if future.empty:
            break
        outcome, exit_price = simulate_trade_dynamic(
            direction, entry, sl, tp, a[i], future,
            be_trigger_atr=be_atr, trail_atr=trail_atr)
        sizing_bal = balance if compound else cfg["account"]["size_usd"]
        lots = position_size(sizing_bal, cfg["account"]["risk_per_trade_pct"],
                             entry, sl, instr["contract_size"],
                             cost_per_lot=trade_cost(1.0, instr))
        cost = trade_cost(lots, instr)
        move = (exit_price - entry) if direction == "buy" else (entry - exit_price)
        pnl = move * instr["contract_size"] * lots - cost
        balance += pnl
        trades.append({"time": df["time"].iloc[i], "dir": direction,
                       "outcome": outcome, "pnl": pnl, "balance": balance})
        i += max_hold
    return BacktestResult(trades=trades,
                          metrics=compute_metrics(trades, cfg["account"]["size_usd"]))
