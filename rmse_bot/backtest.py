from dataclasses import dataclass, field
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
