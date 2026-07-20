# ORACLE — Full Plan & Context (for a second AI to review and improve)

> I am building an experimental self-learning crypto trading predictor called **ORACLE**.
> Below is the COMPLETE context and design. You have no prior knowledge of my project, so
> everything you need is here. At the end are specific questions where I want your critique
> and better ideas. Please be rigorous and honest — do not just agree.

---

## 0. WHAT I'M ASKING YOU

Review this plan and tell me:
1. Is the core design (an online-learning **committee of experts with adaptive weights**) the
   best approach for a *forward-learning, self-improving* predictor — or is there a better one
   (online logistic regression, contextual bandits, Thompson sampling, stacking/meta-learning,
   small neural net, etc.)?
2. How do I make the predictor genuinely **improve accuracy over time** and adapt to regime
   changes, without overfitting the learner itself?
3. How do I beat the **fee wall** (see constraints) — is confidence-gating enough, or do I need
   a fee-aware expected-value threshold?
4. Anything I'm missing that a professional quant would do.

---

## 1. PROJECT BACKGROUND — the existing bot

- I run a **paper-trading** (virtual money) crypto+gold bot. 14 accounts, $5,000 each:
  gold + 13 crypto (BTC, ETH, SOL, ADA, DOGE, OP, SEI, VET, GALA, XTZ, SAND, MANA, HBAR).
- Strategy = **4h regime-gated momentum** ("all-weather"): on the daily timeframe, detect
  regime via EMA100 (up = price>EMA100 & rising, down = price<EMA100 & falling). Then on 4h
  bars: in a DOWN regime take shorts when `rsi_bear & high_vol & strong_trend`; in an UP regime
  take longs when `rsi_overbought & high_vol & strong_trend`. SL = 2×ATR, TP = 1R, max hold 24
  bars, break-even at +1×ATR. Backtested ~14%/yr CAGR on crypto over 8.5 years; trades ~1–6
  times/week across the whole 14-coin book (bursty, regime-gated). Currently ~-2.7% live over
  ~6 weeks of forward paper trading (a choppy period; all coins in down-regime, shorts stopped
  by relief rallies).
- The bot is always-on with a self-learning "brain": a tournament of challenger rules, a
  statistical promotion gate (t-stat), auto-demotion, counterfactual replays, a per-regime
  ledger, an LLM news-sentiment observer, and a graduation gate (must pass 90 days / 100 trades
  / live PF>1.2 / maxDD<25% before any real money).

## 2. WHAT I'VE ALREADY TESTED AND FOUND DEAD (please do NOT re-suggest these)

All tested on my own data with **real fees** and **split-half robustness** (first half AND
second half of history must both be net-positive, else it's "regime luck"):

- **Scalping / any 1–5 minute strategy: DEAD.** 80 configs across RSI-2, Bollinger fade, EMA
  cross, micro-breakout, volume-spike fade. Before ANY fee the gross edge is ~**1 basis point
  per trade**; the cheapest realistic round-trip fee (maker 4 bp) is 3–4× bigger. Low timeframe
  = "fee graveyard", mathematically.
- **SMC / order-blocks / liquidity-sweep / ETS course models: DEAD** on every timeframe. ~95
  tests, zero robust; expectancy ≈ 0 before costs, negative after.
- **Intraday mean-reversion (RSI-2 etc.):** strong raw win rate but dies at taker fees.
- **4 candidate strategies I just tested (all failed):**
  - Daily RSI-2 dip-buy: **56% win rate but −97% net** — biggest lesson: high win rate, still
    loses money (small wins, big 2×ATR stop losses). **Win rate alone is a vanity metric.**
  - CVD taker-flow momentum (1h): 41.5% win, gross ~breakeven, fee eats it → negative.
  - RVOL thrust (1h): 38% win, both halves negative → dead.
  - Weekly cross-sectional rotation: +89% net BUT all profit in the first (bull-market) half,
    second half negative → **regime luck, not a robust edge**; and it's just the same momentum
    premium the bot already trades.
- Adding funding-rate / macro / on-chain as filters: marginal or redundant vs price+regime.

**Conclusion so far:** on free retail data with real fees, 4h regime-gated momentum is the only
robust edge found; everything else is either fee-dead, win-rate-vanity, or a regime-luck re-skin.

## 3. THE NEW GOAL (why ORACLE)

I don't want to keep backtesting fixed rules and finding them dead. I want a **different KIND of
system**: one that **predicts the future, learns forward (online), and improves its accuracy
over time — like a professional trader gaining experience.** It should:
- Make an explicit probabilistic prediction each period ("P(up next 4h) = 68%") + confidence.
- Grade itself when the outcome resolves and adapt.
- Trade when confident (frequency is fine — even 10/day). Win rate to be measured, not assumed.
- Be a **separate, isolated experiment** with its own dashboard — it must NEVER touch the main
  bot's 14 accounts.
- Honest framing: I'm NOT claiming it beats the market. The whole point is it **self-grades** so
  we'll KNOW: ~50% accuracy = no edge (kill it); 55–58%+ = a real, forward-proven adaptive edge.

## 4. ORACLE — the proposed design (full detail)

### 4.1 Core idea
Instead of one fixed rule, run a **committee of 8 simple "analyst" experts**, each casting a
directional vote every bar. A **meta-brain** keeps a trust *weight* per expert and updates it
FORWARD as real outcomes arrive — trusting whichever analysts are right in the CURRENT regime.
Like a trading desk where the head trader listens more to whoever's been right lately.

### 4.2 Data available (all FREE, real-time)
- Binance public API: OHLCV + volume + **taker-buy-base-volume** (kline field 9 — a coarse
  order-flow proxy: net aggressive buyers vs sellers per bar). All coins, 1m–1d, real-time,
  deep history. No paid data, no L2/tick/order-book, no options.
- (Gold via Dukascopy/TwelveData exists but I'm DROPPING gold for this — its feed isn't
  real-time. Focus purely on Binance coins.)
- Chosen timeframe: **1h**, prediction horizon **H = 4 bars (~4 hours ahead)**. (Open to change.)

### 4.3 Features (per bar, all causal / no look-ahead)
close, EMA9, EMA21, EMA50, EMA100, RSI14, RSI2, MACD & signal, ATR14, 20-bar return,
Donchian(20) high/low, RVOL (volume / 20-median), taker_delta ((2·taker_buy − volume) /
20-median-volume), volatility z-score (20-bar realized vol vs its 100-bar mean/std).

### 4.4 The 8 experts (each returns a vote in {−1, 0, +1})
1. `momentum_fast`: sign(EMA9 − EMA21)
2. `trend_slow`: sign(close − EMA100)
3. `macd`: sign(MACD − signal)
4. `rsi_revert`: +1 if RSI14<30, −1 if RSI14>70, else 0
5. `breakout`: +1 if close>Donchian20-high, −1 if close<Donchian20-low, else 0
6. `volume_thrust`: sign(taker_delta) if RVOL≥1.8 else 0
7. `vol_expansion`: sign(EMA9−EMA21) if vol_z>0 else 0
8. `meanrev_micro`: +1 if RSI2<5, −1 if RSI2>95, else 0

### 4.5 The meta-brain — exponential weights / Hedge (the math)
Each expert i has weight wᵢ (init 1.0). Prediction each bar:
```
score = Σ wᵢ·voteᵢ / Σ wᵢ            (score ∈ [−1, +1])
P(up) = 0.5 + 0.5·score              (probability ∈ [0, 1])
confidence = |score|                 (∈ [0, 1])
```
When a prediction's horizon resolves (realized_dir = sign(close[t+H] − close[t])):
```
for each expert:  wᵢ *= exp(eta · voteᵢ · realized_dir) · decay
then renormalise so Σ wᵢ = 1
```
- `eta` (learning rate) ≈ 0.15 — how fast trust shifts to recently-correct experts.
- `decay` ≈ 0.999 — slowly forgets stale performance so it stays adaptive to regime change.
- `voteᵢ · realized_dir` = +1 if the expert was right, −1 if wrong, 0 if it abstained.

### 4.6 Prediction & confidence → output
Every bar produces `{P(up), confidence, per-expert votes, per-expert weights}`, all logged.

### 4.7 Self-grading loop
Each prediction is stored; when H bars pass, it's graded correct/incorrect and the committee
weights are updated. We track **rolling hit-rate** and **calibration** (when it says 65%, does
it hit ~65%?) and Brier score — the honest measures of "is it improving?".

### 4.8 Trade layer (isolated paper account)
When `confidence > threshold` and no open position on that symbol: open a paper trade in
ORACLE's own account, direction = sign(score), SL/TP = ATR-based (e.g. SL 1.5×ATR, TP 2×ATR,
time-stop H bars). Threshold controls frequency: loose → ~10+ trades/day across coins; strict →
fewer, higher-conviction. Fees modelled at 0.10% round-trip (crypto taker).

### 4.9 Isolation & dashboard
Own state files (`oracle_*`), own $5,000 paper account(s), own always-on service on my VPS, and
its OWN "ORACLE" tab on the dashboard showing: live predictions, **per-expert weight bars** (who
the meta-brain trusts right now), a **rolling-accuracy curve** (the key "is it learning?" chart),
calibration, open/closed trades, and equity. It never reads or writes the 14 champion accounts.

### 4.10 The actual code drafted so far (Python)
```python
import numpy as np, pandas as pd
from rmse_bot.indicators import ema, rsi, atr

def build_features(df):
    c = df["close"]; f = pd.DataFrame(index=df.index); f["close"]=c
    f["ema9"]=ema(c,9); f["ema21"]=ema(c,21); f["ema50"]=ema(c,50); f["ema100"]=ema(c,100)
    f["rsi14"]=rsi(c,14); f["rsi2"]=rsi(c,2)
    macd=ema(c,12)-ema(c,26); f["macd"]=macd; f["macd_sig"]=ema(macd,9)
    f["atr"]=atr(df,14); f["ret20"]=c.pct_change(20)
    f["don_hi"]=df["high"].shift(1).rolling(20).max(); f["don_lo"]=df["low"].shift(1).rolling(20).min()
    v=df["volume"]; f["rvol"]=v/v.rolling(20).median()
    tb=df["taker_buy"]; f["taker_delta"]=(2*tb-v)/v.rolling(20).median()
    vol=c.pct_change().rolling(20).std(); f["vol_z"]=(vol-vol.rolling(100).mean())/vol.rolling(100).std()
    return f

def _sgn(x): return 1.0 if x>0 else (-1.0 if x<0 else 0.0)

EXPERTS = {
  "momentum_fast": lambda r: _sgn(r["ema9"]-r["ema21"]),
  "trend_slow":    lambda r: _sgn(r["close"]-r["ema100"]),
  "macd":          lambda r: _sgn(r["macd"]-r["macd_sig"]),
  "rsi_revert":    lambda r: 1.0 if r["rsi14"]<30 else (-1.0 if r["rsi14"]>70 else 0.0),
  "breakout":      lambda r: 1.0 if r["close"]>r["don_hi"] else (-1.0 if r["close"]<r["don_lo"] else 0.0),
  "volume_thrust": lambda r: _sgn(r["taker_delta"]) if r["rvol"]>=1.8 else 0.0,
  "vol_expansion": lambda r: _sgn(r["ema9"]-r["ema21"]) if r["vol_z"]>0 else 0.0,
  "meanrev_micro": lambda r: 1.0 if r["rsi2"]<5 else (-1.0 if r["rsi2"]>95 else 0.0),
}

class Committee:
    def __init__(self, names, eta=0.15, decay=0.999):
        self.names=list(names); self.w={n:1.0 for n in names}; self.eta=eta; self.decay=decay
    def predict(self, votes):
        tot=sum(self.w.values()) or 1.0
        score=sum(self.w[n]*votes.get(n,0.0) for n in self.names)/tot
        return 0.5+0.5*score, abs(score)
    def update(self, votes, realized_dir):
        for n in self.names:
            self.w[n]*=float(np.exp(self.eta*votes.get(n,0.0)*realized_dir))*self.decay
        s=sum(self.w.values()) or 1.0
        for n in self.names: self.w[n]=max(self.w[n]/s,1e-6)
```

## 5. Phases / rollout
- **A (done):** core committee engine written (above), fully isolated, not deployed.
- **B (next):** walk-forward ONLINE preview on ~220 days of 1h data (BTC/ETH/SOL/DOGE/ADA, with
  taker_buy). Process bars in time order; predict, then grade+update when horizons resolve —
  exactly as it would live. Report: rolling accuracy %, calibration, per-expert weight evolution,
  and PnL after 0.10% fees. Go/no-go on the results.
- **C:** if promising, run live paper on the VPS 3–4 weeks with its own self-grading dashboard.
- **D:** only if forward-proven → discuss real-money path (a non-US VPS + Binance testnet first).

## 6. HONEST CONSTRAINTS
- Real fees: crypto taker ≈ 0.10% round-trip, spot ≈ 0.20%. Any edge < fee = dead.
- No paid/infra data (no order-book/L2, no tick data, no options chain). Only OHLCV + volume +
  taker-buy field.
- The efficient-market reality: most simple signals have ~zero edge after fees; the honest hope
  is that *adaptively combining* them + trading only when confident yields a small, real,
  forward-measured edge — not a magic future-teller.
- The learner must not overfit itself (e.g., eta too high = it chases noise; too low = it never
  adapts).

## 7. SPECIFIC QUESTIONS FOR YOU (the second brain)
1. **Meta-learner choice:** Is Hedge/exponential-weights the best online combiner here, or would
   online logistic regression (SGD), a contextual bandit (LinUCB/Thompson), online gradient
   boosting, or a tiny online neural net do meaningfully better for direction prediction? Trade
   off adaptivity vs overfitting.
2. **Expert diversity:** My 8 experts are mostly momentum/mean-reversion/breakout — likely
   correlated. What genuinely *orthogonal* experts should I add using only OHLCV + taker-buy
   volume (e.g., order-flow imbalance features, volatility-regime, time-of-day, cross-asset
   BTC-lead-lag, microstructure proxies)?
3. **Regime-conditioning:** Should expert weights be conditioned on a detected regime (separate
   weight vectors per bull/bear/chop state) rather than one global adaptive weight set?
4. **Fee-aware trading:** Instead of a fixed confidence threshold, should I compute an expected
   value (P(up)·avg_win − P(down)·avg_loss − fee) and only trade when EV > 0? How to estimate the
   win/loss magnitudes online?
5. **Calibration:** Best lightweight online calibration (Platt scaling / isotonic / temperature)
   so the confidence numbers are trustworthy?
6. **Horizon & timeframe:** 1h bars / 4h horizon — or would 15m or 4h be better given the fee
   wall and the need for ~several trades/day?
7. **Anti-overfitting for the online learner itself:** how to validate that ORACLE's *live*
   improvement is real and not just curve-fitting the recent past?
8. **Honest metrics:** beyond hit-rate — Brier score, calibration error, rolling Sharpe of the
   confident trades — what's the right scorecard to decide "keep or kill" after 3–4 weeks live?

Please critique the design, flag anything naive, and propose the strongest version of this
system you can, given the hard constraints (free OHLCV + taker-buy data only, real fees,
isolated paper experiment, must self-grade forward).
