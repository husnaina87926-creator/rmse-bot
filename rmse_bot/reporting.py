"""Daily + cumulative performance reporting for the paper trader."""
from datetime import datetime, timezone


def compute_stats(closed: list, starting_balance: float) -> dict:
    """Aggregate metrics over a list of closed trades (each has pnl, balance_after)."""
    if not closed:
        return {"num_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "total_pnl": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0,
                "balance": round(starting_balance, 2)}
    pnls = [t["pnl"] for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    gross_win, gross_loss = sum(wins), sum(losses)
    equity = [t.get("balance_after") for t in closed if t.get("balance_after") is not None]
    peak, mdd = starting_balance, 0.0
    for b in equity:
        peak = max(peak, b)
        mdd = max(mdd, peak - b)
    return {
        "num_trades": len(closed),
        "wins": len(wins),
        "losses": len([p for p in pnls if p < 0]),
        "win_rate": round(len(wins) / len(closed), 3),
        "total_pnl": round(sum(pnls), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else float("inf"),
        "max_drawdown": round(mdd, 2),
        "balance": round(equity[-1], 2) if equity else round(starting_balance, 2),
    }


def daily_slice(closed: list, date_str: str) -> list:
    """Closed trades whose close_time falls on the given YYYY-MM-DD."""
    return [t for t in closed if str(t.get("close_time", ""))[:10] == date_str]


def render_daily_md(date_str: str, day: dict, cum: dict, open_count: int) -> str:
    pf = "∞" if cum["profit_factor"] == float("inf") else f"{cum['profit_factor']:.2f}"
    return (
        f"# RMSE_BOT — Daily Report {date_str}\n\n"
        f"## Today\n"
        f"- Trades closed: **{day['num_trades']}** (W {day['wins']} / L {day['losses']})\n"
        f"- Today's P&L: **${day['total_pnl']:.2f}**\n"
        f"- Open positions now: {open_count}\n\n"
        f"## Cumulative (since start)\n"
        f"- Balance: **${cum['balance']:.2f}**\n"
        f"- Total trades: {cum['num_trades']}  |  Win rate: {cum['win_rate']:.0%}\n"
        f"- Total P&L: ${cum['total_pnl']:.2f}  |  Profit factor: {pf}\n"
        f"- Max drawdown: ${cum['max_drawdown']:.2f}\n\n"
        f"_Paper (virtual) trading — forward test. Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC._\n"
    )


def render_summary_row(date_str: str, day: dict, cum: dict) -> str:
    """One CSV-ish line appended to the running history summary."""
    return (f"{date_str},{day['num_trades']},{day['total_pnl']:.2f},"
            f"{cum['balance']:.2f},{cum['num_trades']},{cum['win_rate']:.3f}\n")
