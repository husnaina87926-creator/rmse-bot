from rmse_bot.risk import position_size, trade_cost


def test_position_size_basic():
    # balance 100, risk 1% = $1; SL distance 5 price units; contract 100 units/lot
    # lots = 1 / (5 * 100) = 0.002
    lots = position_size(balance=100, risk_pct=1.0, entry=2340, stop=2335, contract_size=100)
    assert round(lots, 6) == 0.002


def test_position_size_zero_distance_returns_zero():
    assert position_size(100, 1.0, 2340, 2340, 100) == 0.0


def test_trade_cost_combines_spread_slippage_commission():
    instr = {"contract_size": 100, "spread_price": 0.30,
             "slippage_price": 0.10, "commission_per_lot": 0.0}
    # (0.30 + 0.10) * 100 * 0.002 lots = 0.08 ; commission 0
    assert round(trade_cost(0.002, instr), 6) == 0.08
