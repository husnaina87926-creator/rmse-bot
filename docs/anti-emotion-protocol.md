# Anti-Emotion Protocol — DESIGN ONLY (not wired to trading)

**Status: DESIGN DOCUMENT.** Nothing in this file is executed by the bot. Any rule here
that touches position size or trading behavior requires explicit owner approval before
being implemented, and would then go through the normal test → forward-test path.

## Why

A human trader's worst losses come from emotional states: revenge trading after a loss,
overconfidence after a streak, freezing in drawdown. The bot has no emotions — but its
OWNER does. This protocol pre-commits, in writing and in advance, how the system should
behave in stress scenarios, so decisions are never made mid-drawdown.

## Pre-committed rules (proposed, NOT active)

1. **Loss-streak throttle** — after 5 consecutive losing trades in one account, halve
   that account's `risk_pct` for the next 10 trades, then restore. (Bounds a bad-regime
   bleed without killing the edge; symmetric restore prevents permanent timidity.)
2. **Drawdown ladder** — account drawdown from peak: at −20% halve risk; at −30% stop
   opening new trades in that account until its rolling last-20 net turns positive.
   The champion keeps trading paper in a shadow copy so recovery is measurable.
3. **No-revenge cooldown** — after any single trade losing ≥ 2× the average loss,
   skip the next signal in that symbol (one candle). Removes "immediately re-enter
   the same fight" behavior.
4. **Streak-euphoria guard** — never raise risk because of a winning streak. Risk
   changes only through the owner or through a forward-proven promotion.
5. **Owner override log** — every manual intervention (config change, forced restart,
   state edit) must be journaled with a reason. The journal already records everything
   the bot does; this extends it to what the human does.

## What already exists (live today, observer-only)

- Health monitor flags an account whose last 20 trades are net negative.
- Auto-demotion un-learns promoted rules whose forward record decays.
- Daily loss cap + max-open-trades already enforced in the paper trader.
- Regime-break detector journals regime flips and volatility breaks.

## Activation path (when owner approves)

1. Implement rule as a pure function with tests (no live wiring).
2. Run as OBSERVER for 30+ days: journal "would have throttled here" events only.
3. Compare throttled-vs-actual paper equity. Activate only if it reduces drawdown
   without reducing net profit materially.
