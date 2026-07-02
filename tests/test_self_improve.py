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


def test_candidate_list_and_chal_account():
    from rmse_bot.self_improve import candidate_list, chal_account
    r = {"direction": "sell", "when": ["a"]}
    old = {"BTCUSDT": {"rule": r}}                             # legacy single-dict format
    got = candidate_list(old, "BTCUSDT")
    assert got[0]["slot"] == 0 and got[0]["rule"] == r
    new = {"BTCUSDT": [{"rule": r, "slot": 0}, {"rule": r, "slot": 2}]}
    assert [c["slot"] for c in candidate_list(new, "BTCUSDT")] == [0, 2]
    assert candidate_list({}, "BTCUSDT") == []
    assert chal_account("btc", 0) == "btc_chal"                # historical name kept
    assert chal_account("btc", 1) == "btc_chal2"
    assert chal_account("btc", 2) == "btc_chal3"


def _write_state(path, balance, pnls):
    import json
    with open(path, "w") as f:
        json.dump({"balance": balance, "open": [],
                   "closed": _closed(pnls), "history": []}, f)


def test_promotion_from_tournament_slot(tmp_path):
    import json
    import os
    from rmse_bot.self_improve import promotion_demotion_pass
    from rmse_bot.journal import read_events
    sd = str(tmp_path)
    base = {"direction": "sell", "when": ["base"], "regime": "down"}
    r1 = {"direction": "buy", "when": ["x"], "regime": "up"}
    r2 = {"direction": "sell", "when": ["y"], "regime": "down"}
    cfg = {"edge_rules": {}, "crypto_rules": {"rules": [base]}}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    json.dump({"BTCUSDT": [{"rule": r1, "slot": 0, "born": now},
                           {"rule": r2, "slot": 1, "born": now}]},
              open(os.path.join(sd, "candidates.json"), "w"))
    _write_state(os.path.join(sd, "btc.json"), 5100, [2.5] * 40)       # champion +100
    _write_state(os.path.join(sd, "btc_chal.json"), 5010, [1] * 10)    # slot0: mid-trial
    _write_state(os.path.join(sd, "btc_chal2.json"), 5300, [7.5] * 40)  # slot1: proven

    promoted, demoted = promotion_demotion_pass(cfg, sd, {"BTCUSDT": "btc"}, 5000)
    assert promoted == [("BTCUSDT", r2)] and demoted == []
    live = json.load(open(os.path.join(sd, "live_rules.json")))
    assert live["BTCUSDT"] == [base, r2]                       # champion rules + promoted
    cands = json.load(open(os.path.join(sd, "candidates.json")))
    assert [c["slot"] for c in cands["BTCUSDT"]] == [0]        # slot1 freed
    assert not os.path.exists(os.path.join(sd, "btc_chal2.json"))
    promos = json.load(open(os.path.join(sd, "promotions.json")))
    assert promos["BTCUSDT"][0]["rule"] == r2                  # list format, per-promotion
    ev = [e for e in read_events(sd) if e["type"] == "candidate_retired"][0]
    assert ev["reason"] == "promoted" and ev["forward_trades"] == 40


def test_discovery_tournament_fills_and_retires(tmp_path, monkeypatch):
    import json
    import os
    import rmse_bot.self_improve as si
    from rmse_bot.journal import read_events
    sd = str(tmp_path)
    cfg = {"edge_rules": {}, "crypto_rules": {"rules": [{"direction": "sell", "when": ["base"]}]}}
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    r0 = {"direction": "buy", "when": ["k0"], "regime": "up"}
    json.dump({"BTCUSDT": {"rule": r0, "born": now}},          # legacy format, slot 0
              open(os.path.join(sd, "candidates.json"), "w"))
    _write_state(os.path.join(sd, "btc_chal.json"), 5005, [1] * 5)     # mid-trial -> sticky

    fresh = [{"rule": {"direction": "sell", "when": ["n1"], "regime": "down"}, "score": 1, "return": 10, "pf": 1.5},
             {"rule": {"direction": "buy", "when": ["n2"], "regime": "up"}, "score": 1, "return": 8, "pf": 1.4}]
    monkeypatch.setattr(si, "top_candidates", lambda *a, **k: [dict(c) for c in fresh])
    log = si.discovery_pass(cfg, sd, {"BTCUSDT": "btc"}, 5000, lambda s: object(), ["BTCUSDT"])
    cands = json.load(open(os.path.join(sd, "candidates.json")))["BTCUSDT"]
    assert sorted(c["slot"] for c in cands) == [0, 1, 2]       # sticky + 2 recruits
    assert cands[0]["rule"] == r0                              # legacy candidate migrated, kept
    born = [e for e in read_events(sd) if e["type"] == "candidate_born"]
    assert len(born) == 2 and any("keeping candidate" in ln for ln in log)

    # slot1 finishes its 30-trade trial without promoting -> retired; nothing new found
    _write_state(os.path.join(sd, "btc_chal2.json"), 4950, [-1.67] * 30)
    monkeypatch.setattr(si, "top_candidates", lambda *a, **k: [])
    log = si.discovery_pass(cfg, sd, {"BTCUSDT": "btc"}, 5000, lambda s: object(), ["BTCUSDT"])
    cands = json.load(open(os.path.join(sd, "candidates.json")))["BTCUSDT"]
    assert sorted(c["slot"] for c in cands) == [0, 2]          # slot1 retired + freed
    assert not os.path.exists(os.path.join(sd, "btc_chal2.json"))
    ret = [e for e in read_events(sd) if e["type"] == "candidate_retired"][0]
    assert ret["reason"] == "trial_complete" and ret["forward_trades"] == 30
    assert ret["forward_net"] == -50.0


def test_brain_scoreboard(tmp_path):
    import os
    from rmse_bot.self_improve import brain_scoreboard
    from rmse_bot.journal import append_event
    sd = str(tmp_path)
    r1 = {"direction": "sell", "when": ["a", "b"], "regime": "down"}
    r2 = {"direction": "sell", "when": ["a", "c"], "regime": "down"}
    append_event(sd, {"type": "candidate_born", "symbol": "BTCUSDT", "rule": r1, "slot": 0})
    append_event(sd, {"type": "candidate_born", "symbol": "BTCUSDT", "rule": r2, "slot": 1})
    append_event(sd, {"type": "candidate_retired", "symbol": "BTCUSDT", "rule": r1,
                      "reason": "promoted", "forward_trades": 35, "forward_net": 300.0})
    append_event(sd, {"type": "candidate_retired", "symbol": "BTCUSDT", "rule": r2,
                      "reason": "trial_complete", "forward_trades": 30, "forward_net": -50.0})
    append_event(sd, {"type": "rule_demoted", "symbol": "BTCUSDT", "rule": r1})
    sb = brain_scoreboard(sd)
    assert sb["totals"] == {"born": 2, "promoted": 1, "trial_complete": 1,
                            "stale": 0, "demoted": 1}
    fa = sb["families"]["cond:a"]                              # shared condition, both rules
    assert fa["born"] == 2 and fa["promoted"] == 1 and fa["demoted"] == 1
    assert fa["survival_rate"] == 0.5 and fa["avg_forward_net"] == 125.0
    fb = sb["families"]["cond:b"]                              # only the promoted rule
    assert fb["survival_rate"] == 1.0
    assert os.path.exists(os.path.join(sd, "scoreboard.json"))
