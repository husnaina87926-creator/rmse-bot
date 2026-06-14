# RMSE_BOT Phase 2 — Exness / MT5 Integration Plan

**Date:** 2026-06-14
**Status:** Planned (do NOT start until strategy is forward-proven). Documentation only — no spend yet.
**Prereq gate:** Proceed only after the free paper trader shows **weeks of acceptable forward results** (e.g., profit factor > 1.2 live, matches backtest direction). Until then, keep improving for free.

**Roman Urdu:** Yeh plan tab amal mein laana jab strategy forward-test mein khud ko saabit kar de. Abhi sirf reference. Code Windows pe chalega (Mac/Linux pe test nahi hota).

---

## 1. Goal
Replace the (delayed, free) Dukascopy live feed with **Exness real-time data via MT5**, and add **real order execution** — first on a **demo** account, later tiny real. Reuse the entire existing engine (edge rules, `risk`, break-even exits, daily reports, paper-trade accounting).

## 2. The hard constraint (decides everything)
The `MetaTrader5` Python package is **Windows-only** and talks to a **running MT5 terminal**. It does NOT run on GitHub Actions / Linux / macOS-Python. So Phase 2 needs a **Windows machine that stays on**.

### Hosting options (pick when ready)
| Option | Cost | Notes |
|---|---|---|
| **Cheap Windows VPS** (Contabo / forex-VPS) — *recommended* | ~$5-10/mo | Native Windows, reliable 24/7, doesn't load the Mac. Hostinger VPS is mostly Linux (Windows needs extra licensing) — prefer a Windows/forex VPS. |
| **Exness free VPS** | $0 (eligibility) | Free MT5 VPS for funded real accounts meeting equity/volume rules → becomes free later. |
| **Free VM on the M4 Mac** | $0 | UTM + Windows 11 ARM + MT5 (x64 via emulation). Works for 15m strategy but fiddly setup + uses Mac resources. Mac must stay on. |

User context: Apple **M4** Mac (ARM, 16GB), can keep always-on. VM route is $0 but technical; VPS is simplest/most reliable.

## 3. Components to build (on the Windows machine)
- `rmse_bot/mt5_connector.py`:
  - `connect(login, password, server)` → init MT5 terminal session (Exness server).
  - `fetch_mt5(symbol, timeframe, n)` → recent candles in our canonical OHLC schema (drop-in replacement for `fetch_dukascopy`).
  - `place_order(symbol, direction, lots, sl, tp, magic)` → market order (Phase 2b).
  - `manage_orders()` → read open positions, modify SL (break-even), close.
- Reuse unchanged: `signal_engine`/`edge_rules`, `risk.py` (sizing/costs), break-even logic, `reporting.py`.
- `scripts/run_live_mt5.py` → the Windows loop (every 15 min): fetch Exness data → signals → execute on demo → log.

## 4. Migration steps (each a gate)
1. **MT5 data only:** point the paper trader at `fetch_mt5` (Exness real-time) instead of Dukascopy. Still virtual money, but **real, fresh prices**. Validate fills/spreads look sane.
2. **Demo execution:** bot places/manages real **demo-account** orders (virtual money, real broker behavior: spread, slippage, requotes). Run for weeks.
3. **Tiny real:** only after good demo results, fund a small real account; same code, smallest lot sizes.

## 5. Safety (mandatory before any real money)
- **Demo-first**, for weeks. Kill switch (a flag/file that halts new orders).
- Reuse: daily loss limit, max open trades. Add: max lot cap, max spread filter (skip if spread too wide), requote/retry handling, `magic` number to tag the bot's trades.
- Optional manual-confirm mode (bot proposes, user approves) for first real trades.
- Health/drift monitor: alert if live results diverge sharply from backtest.

## 6. Cost summary
- Phase 2 testing (demo): VPS ~$5-10/mo **or** $0 via Mac VM **or** $0 Exness VPS once funded.
- No real-money risk until step 3, with smallest possible size.

## 7. Honest caveats
- MT5 code can't be tested in the current Mac/Linux environment — it's written here, run/tested on Windows.
- Exness demo prices ≈ real, but exact fills differ; demo is the proof, not a guarantee.
- This is the path to *accurate data + real execution*; it does not make the edge bigger — risk management + a proven edge still decide outcomes.

## 8. Do-not-proceed-until checklist
- [ ] Paper trader has run several weeks live.
- [ ] Live forward results broadly match backtest (direction + rough PF).
- [ ] Self-learning / feature improvements explored (free) and strategy still holds.
- [ ] User has chosen a Windows host (VPS or Mac VM).
- [ ] Exness account created; **demo** ready.
