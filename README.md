# RMSE_BOT

Professional **intraday analysis bot** for Forex/Gold (XAUUSD, EURUSD). It produces
*realistic* trade signals — accounting for spread, slippage, commission, and position
sizing — explains the reason for every signal, and uses **one shared engine** across
backtesting, live signals, and (later) auto-execution.

> **Honest note / Imaandaar baat:** Koi system guaranteed profit nahi de sakta. Yeh bot
> behtar quality ka analysis deta hai, magar asal faisla **backtest** karega. Risk
> management (1% per trade, stop-loss) hi aap ka asal protector hai. Real paisa sirf
> demo-proof ke baad (Plan 3+).

## Phases

- **Phase 1 (current):** Analyzer / signal bot — zero real-money risk.
- **Phase 2 (later):** Auto-trader via MT5/Exness — demo first, then small real, with
  kill-switch and daily loss limit.

## Plan roadmap

1. **Plan 1 (this repo so far):** Core engine + backtester — *prove the strategy*
2. **Plan 2:** Chart rendering + AI vision (Gemini) + session/news/volatility filters
3. **Plan 3:** Telegram alerts + storage + GitHub Actions deploy (24/7 free)
4. **Plan 4:** Streamlit dashboard

Design spec: [`docs/superpowers/specs/2026-06-13-rmse-bot-design.md`](docs/superpowers/specs/2026-06-13-rmse-bot-design.md)
Plan 1: [`docs/superpowers/plans/2026-06-13-rmse-bot-core-engine.md`](docs/superpowers/plans/2026-06-13-rmse-bot-core-engine.md)

## The analysis brain (4 layers)

1. **Market structure / price action** — swings, trend, Break-of-Structure (the *real* trend, not just EMAs)
2. **Indicators as confluence** — EMA/RSI/ATR confirm, never decide alone
3. **AI vision** *(Plan 2)* — the bot renders its own clean chart and an AI model "looks" at it
4. **Risk/context filters** *(Plan 2)* — session, news, volatility

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run tests

```bash
source .venv/bin/activate
pytest
```

## Run a backtest (real data via yfinance)

```bash
source .venv/bin/activate
python scripts/run_backtest.py
```

Prints metrics per instrument: **win rate, profit factor, max drawdown, expectancy,
total return**. Note: yfinance 15m history is ~60 days; a full 2-3 year backtest uses a
downloaded CSV (added in a later step). The default config uses a $100 account and 1%
risk per trade — change it in [`config.yaml`](config.yaml).

## Project structure

```
rmse_bot/
  config.py         # load settings
  data_feed.py      # OHLC data (CSV + yfinance)
  indicators.py     # EMA, RSI, ATR
  structure.py      # swings, trend, break-of-structure
  risk.py           # position sizing + trade costs
  signal_engine.py  # combines layers -> Signal(direction, entry, sl, tp, confidence, reason)
  backtest.py       # historical simulation + metrics
scripts/
  run_backtest.py   # integration: real data -> report
tests/              # pytest unit tests for every module
```
