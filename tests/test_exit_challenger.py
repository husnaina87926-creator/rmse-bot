"""W1 exit-challenger paired-gate tests."""
from rmse_bot import exit_challenger as ec

CFG = {"exit_challengers": {"enabled": True, "coins": ["BTCUSDT", "ETHUSDT"],
                            "variants": {"breakeven_1.0": {"be_atr": 1.0}, "trail_1.5": {"trail_atr": 1.5}},
                            "gate": {"min_paired": 15, "t_stat": 2.0}}}


def test_specs_only_for_configured_coins():
    assert len(ec.specs_for(CFG, "BTCUSDT")) == 2
    assert ec.specs_for(CFG, "DOGEUSDT") == []            # not a configured exit-challenger coin
    labels = {s[0] for s in ec.specs_for(CFG, "ETHUSDT")}
    assert labels == {"breakeven_1.0", "trail_1.5"}


def test_trade_R_from_pnl_and_risk():
    assert ec.trade_R({"pnl": 500.0, "balance_after": 5500.0}, 10.0) == 1.0    # risk=0.1*5000=500
    assert ec.trade_R({"pnl": -500.0, "balance_after": 4500.0}, 10.0) == -1.0
    assert ec.trade_R({"pnl": 0.0, "balance_after": 5000.0}, 10.0) == 0.0


def test_paired_diffs_matches_on_entry_only():
    champ = [{"open_time": "2026-07-01 00:00", "pnl": -500.0, "balance_after": 4500.0},   # R -1
             {"open_time": "2026-07-02 00:00", "pnl": -500.0, "balance_after": 4000.0}]   # unmatched
    chal = [{"open_time": "2026-07-01 00:00", "pnl": 0.0, "balance_after": 5000.0}]       # R 0 -> diff +1
    d = ec.paired_diffs(champ, chal, 10.0)
    assert d == [1.0]                                     # only the shared entry pairs


def test_paired_verdict_promote_hold_retire():
    promote = ec.paired_verdict([0.2, 0.3, 0.4] * 6)      # n=18, mean +0.3, both halves +, tight
    assert promote["verdict"] == "promote" and promote["both_halves"] is True and promote["t"] >= 2.0
    retire = ec.paired_verdict([-0.2, -0.3, -0.4] * 6)
    assert retire["verdict"] == "retire"
    thin = ec.paired_verdict([0.3] * 10)                  # n<15
    assert thin["verdict"] == "hold"
    mixed = ec.paired_verdict([0.5] * 8 + [-0.5] * 8)     # halves disagree
    assert mixed["verdict"] == "hold" and mixed["both_halves"] is False


def test_pooled_verdict_pools_across_coins():
    # 8 winning paired trades on btc + 8 on eth for breakeven -> pooled n=16 -> promote
    def acct(r):
        return [{"open_time": f"2026-07-{i:02d} 00:00", "pnl": r * 500, "balance_after": 5000 + r * 500}
                for i in range(1, 9)]
    closed = {
        "btc": acct(-1.0), "btc_exit_breakeven_1_0": acct(0.0), "btc_exit_trail_1_5": [],
        "eth": acct(-1.0), "eth_exit_breakeven_1_0": acct(0.0), "eth_exit_trail_1_5": [],
    }
    v = ec.pooled_verdict(CFG, closed, 10.0)
    assert v["breakeven_1.0"]["n"] == 16 and v["breakeven_1.0"]["verdict"] == "promote"
