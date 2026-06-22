from rmse_bot.self_improve import rules_for, should_promote


def test_rules_for_prefers_live_then_config():
    cfg = {"edge_rules": {"XAUUSD": [{"direction": "buy", "when": ["a"]}]},
           "crypto_rules": {"rules": [{"direction": "sell", "when": ["b"]}]}}
    live = {"BTCUSDT": [{"direction": "buy", "when": ["x"]}]}
    assert rules_for("XAUUSD", cfg, live)[0]["when"] == ["a"]      # config (gold)
    assert rules_for("BTCUSDT", cfg, live)[0]["when"] == ["x"]     # live override
    assert rules_for("ETHUSDT", cfg, {})[0]["when"] == ["b"]       # crypto fallback


def test_should_promote_requires_forward_proof():
    champ = {"balance": 5100, "closed": [{}] * 40}                  # +100
    assert should_promote(champ, {"balance": 5300, "closed": [{}] * 40}, 5000, 30) is True   # beats + enough trades
    assert should_promote(champ, {"balance": 5300, "closed": [{}] * 10}, 5000, 30) is False  # too few trades
    assert should_promote(champ, {"balance": 5050, "closed": [{}] * 40}, 5000, 30) is False  # doesn't beat champ
    assert should_promote(champ, {"balance": 4900, "closed": [{}] * 40}, 5000, 30) is False  # losing
