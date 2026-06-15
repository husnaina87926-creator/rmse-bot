from rmse_bot.portfolio import select_portfolio, portfolio_rules


def test_select_portfolio_picks_distinct_entries():
    strategies = [
        {"direction": "buy", "entry": ["a", "b"], "score": 100},
        {"direction": "buy", "entry": ["b", "a"], "score": 90},   # same set -> skip
        {"direction": "buy", "entry": ["c"], "score": 80},
        {"direction": "sell", "entry": ["a", "b"], "score": 70},  # diff direction -> keep
    ]
    chosen = select_portfolio(strategies, max_n=4)
    assert len(chosen) == 3                       # the duplicate (b,a) dropped
    assert chosen[0]["entry"] == ["a", "b"]


def test_select_portfolio_respects_max_n():
    strategies = [{"direction": "buy", "entry": [c], "score": i}
                  for i, c in enumerate("abcdef")]
    assert len(select_portfolio(strategies, max_n=3)) == 3


def test_portfolio_rules_format():
    chosen = [{"direction": "buy", "entry": ["x", "y"]},
              {"direction": "sell", "entry": ["z"]}]
    rules = portfolio_rules(chosen)
    assert rules == [{"direction": "buy", "when": ["x", "y"]},
                     {"direction": "sell", "when": ["z"]}]
