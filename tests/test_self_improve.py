import datetime as dt

from rmse_bot.self_improve import (
    rules_for, should_promote, should_demote, keep_candidate,
)


def test_rules_for_prefers_live_then_config():
    cfg = {"edge_rules": {"XAUUSD": [{"direction": "buy", "when": ["a"]}]},
           "crypto_rules": {"rules": [{"direction": "sell", "when": ["b"]}]}}
    live = {"BTCUSDT": [{"direction": "buy", "when": ["x"]}]}
    assert rules_for("XAUUSD", cfg, live)[0]["when"] == ["a"]      # config (gold)
    assert rules_for("BTCUSDT", cfg, live)[0]["when"] == ["x"]     # live override
    assert rules_for("ETHUSDT", cfg, {})[0]["when"] == ["b"]       # crypto fallback


def _closed(pnls):
    return [{"pnl": p} for p in pnls]


def test_should_promote_requires_forward_proof_and_significance():
    champ = {"balance": 5100, "closed": _closed([10] * 40)}          # +100
    steady = {"balance": 5300, "closed": _closed([7.5] * 40)}        # +300, zero variance
    assert should_promote(champ, steady, 5000, 30) is True           # beats + enough + steady

    few = {"balance": 5300, "closed": _closed([30] * 10)}
    assert should_promote(champ, few, 5000, 30) is False             # too few trades

    weaker = {"balance": 5050, "closed": _closed([1.25] * 40)}
    assert should_promote(champ, weaker, 5000, 30) is False          # doesn't beat champ

    losing = {"balance": 4900, "closed": _closed([-2.5] * 40)}
    assert should_promote(champ, losing, 5000, 30) is False          # losing

    # NEW: a lucky/noisy challenger (one huge win, rest losses) fails the t-stat gate
    noisy = {"balance": 5300, "closed": _closed([1000] + [-17.9] * 39)}
    assert should_promote(champ, noisy, 5000, 30) is False


def test_should_demote_on_forward_decay():
    promoted_at = "2026-06-01T00:00:00+00:00"
    old = [{"pnl": 50, "close_time": "2026-05-20 04:00:00+00:00"}] * 30
    bad_since = [{"pnl": -10, "close_time": "2026-06-10 04:00:00+00:00"}] * 20
    good_since = [{"pnl": 10, "close_time": "2026-06-10 04:00:00+00:00"}] * 20

    assert should_demote({"closed": old + bad_since}, promoted_at) is True    # decayed
    assert should_demote({"closed": old + good_since}, promoted_at) is False  # healthy
    assert should_demote({"closed": old + bad_since[:5]}, promoted_at) is False  # too few since


def test_keep_candidate_stickiness():
    fresh = {"rule": {"direction": "buy", "when": ["a"]},
             "born": dt.datetime.now(dt.timezone.utc).isoformat()}
    trial = {"closed": _closed([1] * 5)}                       # only 5 forward trades
    done = {"closed": _closed([1] * 30)}                       # full trial
    stale = dict(fresh, born=(dt.datetime.now(dt.timezone.utc)
                              - dt.timedelta(days=60)).isoformat())

    assert keep_candidate(fresh, trial) is True                # mid-trial: keep
    assert keep_candidate(fresh, done) is False                # trial complete: replaceable
    assert keep_candidate(stale, trial) is False               # too old: replaceable
    assert keep_candidate(None, trial) is False                # nothing to keep
