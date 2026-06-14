from rmse_bot.config import load_config


def test_load_config_reads_account_defaults():
    cfg = load_config("config.yaml")
    assert cfg["account"]["size_usd"] == 100
    assert cfg["account"]["risk_per_trade_pct"] == 3.0
    assert cfg["instruments"]["XAUUSD"]["contract_size"] == 100
