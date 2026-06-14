from rmse_bot.reporting import compute_stats, daily_slice, render_daily_md


def _trade(pnl, balance_after, close_time):
    return {"symbol": "XAUUSD", "direction": "buy", "pnl": pnl,
            "balance_after": balance_after, "close_time": close_time, "outcome": "tp"}


def test_compute_stats_empty():
    s = compute_stats([], starting_balance=100)
    assert s["num_trades"] == 0
    assert s["balance"] == 100


def test_compute_stats_basic():
    closed = [
        _trade(5.0, 105.0, "2026-06-14 10:00:00+00:00"),
        _trade(-2.0, 103.0, "2026-06-14 12:00:00+00:00"),
        _trade(4.0, 107.0, "2026-06-15 09:00:00+00:00"),
    ]
    s = compute_stats(closed, starting_balance=100)
    assert s["num_trades"] == 3
    assert s["wins"] == 2 and s["losses"] == 1
    assert s["total_pnl"] == 7.0
    assert s["profit_factor"] == round(9 / 2, 2)   # gross win 9 / gross loss 2
    assert s["balance"] == 107.0
    assert s["max_drawdown"] == 2.0                 # peak 105 -> 103


def test_daily_slice_filters_by_date():
    closed = [
        _trade(5.0, 105.0, "2026-06-14 10:00:00+00:00"),
        _trade(4.0, 109.0, "2026-06-15 09:00:00+00:00"),
    ]
    day = daily_slice(closed, "2026-06-14")
    assert len(day) == 1
    assert day[0]["pnl"] == 5.0


def test_render_daily_md_contains_key_numbers():
    day = compute_stats(daily_slice([_trade(5.0, 105.0, "2026-06-14 10:00:00+00:00")],
                                    "2026-06-14"), 100)
    cum = compute_stats([_trade(5.0, 105.0, "2026-06-14 10:00:00+00:00")], 100)
    md = render_daily_md("2026-06-14", day, cum, open_count=1)
    assert "Daily Report 2026-06-14" in md
    assert "105.00" in md
