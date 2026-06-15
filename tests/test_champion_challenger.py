from rmse_bot.champion_challenger import build_accounts, compare_accounts


def test_build_accounts_champion_only_without_registry():
    cfg = {"edge_rules": {"XAUUSD": [{"direction": "buy", "when": ["trend_up"]}]}}
    accts = build_accounts(cfg, registry=None)
    assert len(accts) == 1
    assert accts[0]["name"] == "champion"


def test_build_accounts_adds_challenger_with_candidate():
    cfg = {"edge_rules": {"XAUUSD": [{"direction": "buy", "when": ["trend_up", "rsi_overbought"]}]}}
    registry = {"promotions": [
        {"symbol": "XAUUSD", "direction": "sell", "candidate": ["high_vol", "sweep_up"]},
    ]}
    accts = build_accounts(cfg, registry)
    assert len(accts) == 2
    chal = accts[1]
    # challenger keeps champion rule AND adds the candidate
    whens = [r["when"] for r in chal["rules"]["XAUUSD"]]
    assert ["trend_up", "rsi_overbought"] in whens
    assert ["high_vol", "sweep_up"] in whens
    # champion must be untouched
    assert len(accts[0]["rules"]["XAUUSD"]) == 1


def test_build_accounts_skips_untraded_symbol():
    cfg = {"edge_rules": {"XAUUSD": [{"direction": "buy", "when": ["trend_up"]}]}}
    registry = {"promotions": [
        {"symbol": "EURUSD", "direction": "buy", "candidate": ["rsi_oversold"]},  # dropped symbol
    ]}
    accts = build_accounts(cfg, registry)
    assert len(accts) == 1     # EURUSD challenger skipped


def test_compare_accounts_metrics():
    states = [
        ("champion", {"balance": 105.0, "open": [],
                      "closed": [{"pnl": 3.0}, {"pnl": -1.0}, {"pnl": 3.0}]}),
        ("challenger_1", {"balance": 98.0, "open": [1],
                          "closed": [{"pnl": -2.0}]}),
    ]
    rows = compare_accounts(states)
    champ = rows[0]
    assert champ["trades"] == 3
    assert champ["win"] == round(2 / 3, 2)
    assert champ["pnl"] == 5.0
