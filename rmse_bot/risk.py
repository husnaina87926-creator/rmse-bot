def position_size(balance: float, risk_pct: float, entry: float,
                  stop: float, contract_size: float) -> float:
    risk_amount = balance * (risk_pct / 100.0)
    distance = abs(entry - stop)
    if distance == 0:
        return 0.0
    return risk_amount / (distance * contract_size)


def trade_cost(lots: float, instr: dict) -> float:
    spread = instr.get("spread_price", 0.0)
    slippage = instr.get("slippage_price", 0.0)
    contract = instr["contract_size"]
    commission = instr.get("commission_per_lot", 0.0)
    return (spread + slippage) * contract * lots + commission * lots
