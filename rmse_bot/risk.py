def position_size(balance: float, risk_pct: float, entry: float,
                  stop: float, contract_size: float,
                  cost_per_lot: float = 0.0) -> float:
    """Lots such that a full stop-out loses exactly risk_pct of balance.
    cost_per_lot (spread/slippage/commission for ONE lot) is included in the risk
    budget so the REALIZED loss matches the configured risk — without it every
    stop-out overshoots (e.g. -10.4% on a 10% setting)."""
    risk_amount = balance * (risk_pct / 100.0)
    distance = abs(entry - stop)
    denom = distance * contract_size + max(cost_per_lot, 0.0)
    if denom == 0:
        return 0.0
    return risk_amount / denom


def trade_cost(lots: float, instr: dict) -> float:
    spread = instr.get("spread_price", 0.0)
    slippage = instr.get("slippage_price", 0.0)
    contract = instr["contract_size"]
    commission = instr.get("commission_per_lot", 0.0)
    return (spread + slippage) * contract * lots + commission * lots
