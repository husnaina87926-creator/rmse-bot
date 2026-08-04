"""P3 governor + P6 discovery-quality gate tests (RMSE upgrade build)."""
from rmse_bot import governor as gov
from rmse_bot.config import load_config

CFG = {"governor": {"enabled": True, "max_concurrent_same_dir": 5, "corr_sizing_dark": True,
                    "day_loss_flag_pct": 15}}


def test_count_same_dir_crypto_only():
    open_by = {
        "btc": [{"symbol": "BTCUSDT", "direction": "sell"}],
        "eth": [{"symbol": "ETHUSDT", "direction": "sell"}],
        "gold": [{"symbol": "XAUUSD", "direction": "sell"}],      # not crypto -> excluded
        "op": [{"symbol": "OPUSDT", "direction": "buy"}],         # other direction
    }
    assert gov.count_same_dir(open_by, "sell") == 2               # btc + eth (gold excluded)
    assert gov.count_same_dir(open_by, "buy") == 1


def test_cap_enforces_concurrent_limit():
    assert gov.cap_allows(CFG, 4) is True                          # 4 < 5 -> allowed
    assert gov.cap_allows(CFG, 5) is False                         # at cap -> blocked
    assert gov.cap_allows({"governor": {"enabled": False}}, 99) is True   # disabled -> never blocks


def test_dark_size_factor_sqrt():
    assert gov.dark_size_factor(CFG, 1) == 1.0
    assert gov.dark_size_factor(CFG, 4) == 0.5                     # sqrt(1/4)
    assert gov.dark_size_factor(CFG, 9) == 0.333
    assert gov.sizing_is_dark(CFG) is True                         # measure-only, no live change


def test_day_loss_flag_inert_threshold():
    assert gov.day_loss_flagged(CFG, -16.0) is True               # exceeds -15%
    assert gov.day_loss_flagged(CFG, -10.0) is False
    # the flag never blocks trading — it is a Phase-2 readiness signal only (asserted by design)


def test_governor_enforce_cap_reverts_and_journals(tmp_path):
    import json
    cfg = {"governor": {"enabled": True, "max_concurrent_same_dir": 5, "corr_sizing_dark": True},
           "crypto_rules": {"symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "OPUSDT", "SEIUSDT"]}}
    for nm in ["btc", "eth", "sol", "ada", "op"]:                 # 5 champions already short crypto
        json.dump({"balance": 5000, "open": [{"symbol": nm.upper() + "USDT", "direction": "sell",
                   "open_time": "T" + nm}], "closed": [], "history": []},
                  open(tmp_path / f"{nm}.json", "w"))
    ev = []
    st = {"balance": 5000, "open": [{"symbol": "SEIUSDT", "direction": "sell", "open_time": "Tsei"}], "closed": []}
    gov.enforce_after_step(cfg, str(tmp_path), "sei", st, before_open=[], journal_fn=ev.append)
    assert st["open"] == []                                       # 6th same-dir -> reverted
    assert ev[-1]["type"] == "governor_skipped" and ev[-1]["open_same_dir"] == 5 and ev[-1]["cap"] == 5

    (tmp_path / "op.json").unlink()                              # now only 4 existing shorts
    ev2 = []
    st2 = {"balance": 5000, "open": [{"symbol": "SEIUSDT", "direction": "sell", "open_time": "Tsei2"}], "closed": []}
    gov.enforce_after_step(cfg, str(tmp_path), "sei", st2, before_open=[], journal_fn=ev2.append)
    assert len(st2["open"]) == 1                                  # within cap -> KEPT (dark, never reverted)
    assert ev2[-1]["type"] == "governor_dark_size" and ev2[-1]["would_size_factor"] == gov.dark_size_factor(cfg, 5)


def test_p6_min_conditions_config_present():
    cfg = load_config("config.yaml")
    assert cfg.get("discovery", {}).get("min_conditions", 2) >= 2  # single-condition candidates rejected
