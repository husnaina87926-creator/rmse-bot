# RMSE_BOT — Design Spec

**Date:** 2026-06-13
**Status:** Approved design (pre-implementation)
**Owner:** Mirza Husnain (beginner / non-coder — all code written & explained by assistant)
**Language note (Roman Urdu):** Yeh spec hum dono ka likha hua reference hai. Technical hissa English mein hai, har section ke neeche Roman Urdu mein "Matlab" diya hai taake aap asaani se review kar saken.

---

## 1. Goal / Maqsad

Ek professional **intraday analysis bot** for Forex/Gold that produces *realistic* trade signals — accounting for fees, spread, leverage, slippage — explains the **reason** for every signal, and uses **one shared engine** across backtest, live signals, and (later) auto-execution.

**Matlab:** Aisa bot jo asal trading jaisa sahi analysis de (sirf indicator ka tota nahi), har signal ki wajah bataye, aur jo engine backtest mein chale wahi live mein bhi — taake nateeje jhoote na hon.

### Non-goals (abhi nahi)
- Guaranteed profit ka koi dawa nahi. (Honest: koi system yeh nahi de sakta.)
- Scalping (1-5 min) nahi — free hosting ki delay isay barbaad karti hai.
- Phase 1 mein asal paise se trade execution **nahi** — sirf signals.

---

## 2. Scope & Phases

### Phase 1 — Analyzer / Signal Bot (yeh spec ka focus)
Analysis brain + backtester + Telegram alerts + dashboard. **Asal paisa: zero risk.**

### Phase 2 — Auto-Trader (alag spec banega baad mein)
Same engine ko MT5 (Exness) se jodna → pehle **demo account**, proof ke baad chhota real. Kill-switch + daily loss limit + circuit breakers. Always-on host (Oracle Cloud free VM ya local machine).

**Key principle:** Phase 1 ka engine throwaway nahi — Phase 2 wahi `signal_engine.py` + `risk.py` reuse karega. Isliye realism (fees/leverage) abhi se build hoga.

---

## 3. Market & Instruments

- **Primary:** XAUUSD (Gold), EURUSD
- **Optional (config toggle):** GBPUSD
- **Timeframes:** 1H (trend/context) + 15m (entry) — multi-timeframe confluence
- **Sessions:** London + New York only (best liquidity for gold/forex)

---

## 4. Analysis Brain — 4 Layers

Har candle close pe pipeline chalta hai. Output = **Confidence score (0-100%)** + direction (BUY/SELL/NONE) + reasoning text.

### Layer 1 — Market Structure / Price Action (asal trend)
- Swing high/low detection
- Trend classification: Higher-High/Higher-Low = uptrend; Lower-High/Lower-Low = downtrend; warna range
- **Break of Structure (BOS)** & **Change of Character (CHoCH)** detection (Smart Money Concepts)
- Support/Resistance + Supply/Demand zones
- **Yeh decide karta hai ke direction kya hai — EMA nahi.**

### Layer 2 — Indicators as Confluence (gawah, faisla nahi)
- EMA (9/21/200), RSI(14), ATR(14)
- Sirf Layer 1 ki tasdeeq/strength ke liye. Akele inpe signal nahi banega.

### Layer 3 — AI Vision (bot chart ko "dekhta" hai)
- `chart_render.py` ek clean chart **image** banata hai (candles + EMAs + marked structure/zones)
- Image + structured context (trend, zones, indicators) Gemini vision model ko jaata hai
- AI returns: agree/disagree with the setup, visual patterns it sees, risk notes, and a confidence contribution + reasoning
- **AI calls sirf tab jab Layer 1+2 ek candidate flag karein** (free-tier limits bachane ke liye)
- **Graceful degradation:** AI unavailable/over-limit ho to bot Layer 1+2 pe chalta rahe (signal banega magar "AI: skipped" note ke saath)

### Layer 4 — Risk / Context Filters
- **Session filter:** sirf London/NY hours
- **News filter:** high-impact events (NFP, CPI, FOMC) ke aas-paas trade band (free economic calendar)
- **Volatility/spread filter:** spread bohat wide ya ATR bohat ghair-maamoli ho to skip

### Final Decision
Weighted confidence = f(structure_strength, indicator_confluence, ai_confidence, filters_pass).
Signal sirf tab jab `confidence >= threshold` (default 70%, config).

---

## 5. Realism / Risk Engine (`risk.py`) — backtest == live

Yeh module backtest AUR live dono use karenge taake numbers match karein.

- **Spread** (Exness instrument-wise; configurable pips)
- **Commission** per lot (Exness account type)
- **Swap** (overnight fee) agar trade roll-over ho
- **Slippage** model (entry/exit pe estimated)
- **Leverage & margin** check (Exness Pakistan high leverage — risk note)
- **Position/lot sizing:** auto from `risk_per_trade%` and SL distance
- **SL/TP:** ATR-based, default **1:2 risk-reward**
- **Circuit breakers:** `max_daily_loss`, `max_open_trades`

**Defaults (config, badal sakte hain):**
- Account size: **$100**
- Risk per trade: **1%** ($1)
- Risk-reward: **1:2**
- Confidence threshold: **70%**

---

## 6. Modules (single-responsibility files)

| File | Responsibility | Depends on |
|------|----------------|-----------|
| `config.yaml` / `.env` | settings + API keys (secrets) | — |
| `data_feed.py` | fetch OHLC 15m+1h | Twelve Data free API |
| `structure.py` | swings, BOS/CHoCH, zones | data_feed |
| `indicators.py` | EMA/RSI/ATR | pandas-ta |
| `chart_render.py` | clean chart image | mplfinance |
| `ai_vision.py` | image → Gemini → analysis | chart_render, Gemini API |
| `filters.py` | session/news/volatility | free calendar API |
| `risk.py` | lot size, fees, SL/TP (shared) | config |
| `signal_engine.py` | 4 layers → confidence → signal + reason | all above |
| `backtest.py` | historical run + metrics + walk-forward | signal_engine, risk |
| `storage.py` | save signals/trades/journal | SQLite or Supabase free |
| `telegram_bot.py` | send chart+signal+reason; commands | python-telegram-bot |
| `dashboard/` | Streamlit UI (signals, history, report) | storage |
| `main.py` | orchestrates one run for all instruments | signal_engine, telegram, storage |
| `.github/workflows/run.yml` | cron every 15 min | main.py |

---

## 7. Data Flow

```
GitHub Actions (cron 15m)
   -> main.py (loop over instruments)
       -> data_feed (15m + 1h candles)
       -> structure + indicators
       -> chart_render -> ai_vision   (only if candidate)
       -> filters (session/news/vol)
       -> signal_engine -> confidence + BUY/SELL/NONE + reason
           if signal:
              -> risk (lot, SL, TP)
              -> storage (save signal + journal)
              -> telegram_bot (alert with chart image + reason)
Dashboard (Streamlit) <- reads storage (live signals, history, backtest report)
```

---

## 8. Backtesting

- Historical: **2-3 years**, 15m + 1H
- Uses the **exact same** `signal_engine` + `risk` as live
- **Metrics:** Win rate, **Profit Factor, Max Drawdown, Expectancy, Sharpe**, total return, equity curve
- **Walk-forward analysis** (in-sample optimize, out-of-sample validate) to fight overfitting
- **Trade journal:** har trade — entry/exit, reason, chart snapshot, P/L
- Output: report viewable in dashboard + saved file

**Gate:** Live/real money ki taraf tab hi badhenge jab backtest metrics acceptable hon (e.g., Profit Factor > 1.3, Max DD manageable). Warna strategy revise — **bina paisa khoye.**

---

## 9. Free Hosting Stack (100% free, no credit card)

| Concern | Service | Notes |
|---------|---------|-------|
| Scheduler/run | **GitHub Actions** | cron every 15m; public repo = unlimited minutes |
| Dashboard | **Streamlit Community Cloud** | free hosting |
| Market data | **Twelve Data** free tier | XAU/USD, EUR/USD intraday; free API key |
| AI vision | **Google Gemini** free tier | vision; generous free daily limit |
| Alerts | **Telegram Bot** | free, push notifications |
| Storage/shared state | **SQLite/JSON in repo (default)**, Supabase free optional later | start simple; add Supabase only if needed |
| Economic calendar | free API (e.g., public calendar) | news filter |

**Secrets:** GitHub Secrets + Streamlit secrets mein rakhe jayenge. **Koi key code mein hardcode nahi** (.env gitignored).

---

## 10. Configuration (`config.yaml`)

```yaml
instruments: [XAUUSD, EURUSD]    # GBPUSD optional
timeframes: { trend: 1h, entry: 15m }
account: { size_usd: 100, risk_per_trade_pct: 1.0 }
risk: { reward_ratio: 2.0, max_daily_loss_pct: 5.0, max_open_trades: 2 }
signal: { confidence_threshold: 70 }
sessions: [london, newyork]
news_filter: { enabled: true, block_minutes_around: 30 }
ai_vision: { enabled: true, only_on_candidate: true }
exness: { account_type: standard, spread_pips: {...}, commission_per_lot: {...} }
```

---

## 11. Security & Safety

- API keys → env/secrets only; `.env` in `.gitignore`
- `gitleaks` check before any push
- Input/data validation on feeds (bad/missing candles handled)
- Phase 2 only: demo-first, kill-switch, daily loss limit, manual confirmation option

---

## 12. Honest Caveats (likhna zaroori)

1. **Koi guaranteed profit nahi.** Structure + AI quality behtar karte hain, jeet pakki nahi.
2. **Backtest faisla karega**, hawa nahi. Bad numbers = strategy badlo.
3. **Risk management** (1% rule, SL) hi asal protector hai.
4. Free tiers ki **limits** hain; system gracefully degrade karta hai.
5. **Gold (XAUUSD) volatile** hai — high leverage do-dhaari talwar.
6. Real money sirf demo proof ke baad (Phase 2).

---

## 12a. Build Order (prove-before-deploy)

Strategy ko deploy karne se PEHLE prove karenge:
1. `data_feed` + `indicators` + `structure`
2. `risk` + `signal_engine` (4-layer brain core; AI vision stub)
3. `backtest` + metrics + walk-forward → **PROVE on 2-3yr data**
4. (gate) numbers acceptable? haan → aage; nahi → strategy revise
5. `chart_render` + `ai_vision` (Gemini)
6. `telegram_bot` + `storage`
7. `dashboard` (Streamlit)
8. `.github/workflows/run.yml` (deploy, cron 15m)

Prerequisite (step 0): free accounts/keys setup — Telegram bot token, Twelve Data, Gemini. Assistant guides each.

## 13. Open Items (Phase 2 spec mein resolve honge)
- MT5/Exness execution connector
- Always-on host choice (Oracle free VM vs local)
- Live monitoring/alerting for the auto-trader
- Real-account onboarding checklist
