"""ORACLE — an online-learning, regime-adaptive COMMITTEE predictor (EXPERIMENT).

A different KIND of system from the backtest-and-freeze bot: instead of picking one
fixed rule, ORACLE runs a committee of simple "analyst" experts, each casting a
directional vote every bar. A meta-layer (exponential-weights / Hedge) keeps a trust
weight per expert and updates it FORWARD as real outcomes arrive — trusting whichever
analysts have been right in the CURRENT regime. It logs every prediction with a
confidence, then grades itself when the horizon resolves, so its live accuracy is
measurable and self-improving.

This is deliberately ISOLATED: its own state files (oracle_*), its own accounts, never
touches the champion bot. It is an experiment to MEASURE — honest, not a promise.
Professionals really do run adaptive online learners; whether THIS one beats fees is
exactly what its self-grading dashboard will tell us.
"""
import numpy as np
import pandas as pd

from rmse_bot.indicators import ema, rsi, atr


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Rich per-bar features the experts read (all causal, no look-ahead)."""
    c = df["close"]
    f = pd.DataFrame(index=df.index)
    f["close"] = c
    f["ema9"] = ema(c, 9); f["ema21"] = ema(c, 21)
    f["ema50"] = ema(c, 50); f["ema100"] = ema(c, 100)
    f["rsi14"] = rsi(c, 14); f["rsi2"] = rsi(c, 2)
    macd = ema(c, 12) - ema(c, 26); f["macd"] = macd; f["macd_sig"] = ema(macd, 9)
    f["atr"] = atr(df, 14)
    f["ret20"] = c.pct_change(20)
    f["don_hi"] = df["high"].shift(1).rolling(20).max()
    f["don_lo"] = df["low"].shift(1).rolling(20).min()
    v = df["volume"] if "volume" in df else pd.Series(1.0, index=df.index)
    f["rvol"] = v / v.rolling(20).median()
    tb = df["taker_buy"] if "taker_buy" in df else v * 0.5
    f["taker_delta"] = (2 * tb - v) / v.rolling(20).median()
    vol = c.pct_change().rolling(20).std()
    f["vol_z"] = (vol - vol.rolling(100).mean()) / vol.rolling(100).std()
    return f


# ---- the analysts: each returns a directional vote in [-1, +1] from one feature row ----

def _sgn(x):
    return 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)


EXPERTS = {
    "momentum_fast": lambda r: _sgn(r["ema9"] - r["ema21"]),
    "trend_slow":    lambda r: _sgn(r["close"] - r["ema100"]),
    "macd":          lambda r: _sgn(r["macd"] - r["macd_sig"]),
    "rsi_revert":    lambda r: (1.0 if r["rsi14"] < 30 else (-1.0 if r["rsi14"] > 70 else 0.0)),
    "breakout":      lambda r: (1.0 if r["close"] > r["don_hi"] else (-1.0 if r["close"] < r["don_lo"] else 0.0)),
    "volume_thrust": lambda r: (_sgn(r["taker_delta"]) if r["rvol"] >= 1.8 else 0.0),
    "vol_expansion": lambda r: (_sgn(r["ema9"] - r["ema21"]) if r["vol_z"] > 0 else 0.0),
    "meanrev_micro": lambda r: (1.0 if r["rsi2"] < 5 else (-1.0 if r["rsi2"] > 95 else 0.0)),
}


class Committee:
    """Exponential-weights (Hedge) over experts. Trust adapts forward to who's right now."""

    def __init__(self, names, eta: float = 0.15, decay: float = 0.999):
        self.names = list(names)
        self.w = {n: 1.0 for n in self.names}
        self.eta = eta
        self.decay = decay          # slowly forgets stale performance -> stays adaptive

    def predict(self, votes: dict):
        """-> (p_up in [0,1], confidence in [0,1]). Weighted committee vote."""
        tot = sum(self.w.values()) or 1.0
        score = sum(self.w[n] * votes.get(n, 0.0) for n in self.names) / tot
        p_up = 0.5 + 0.5 * score    # score in [-1,1] -> prob in [0,1]
        return p_up, abs(score)

    def update(self, votes: dict, realized_dir: float):
        """Hedge update: reward each expert by whether its last vote matched reality."""
        for n in self.names:
            v = votes.get(n, 0.0)
            reward = v * realized_dir            # +1 right, -1 wrong, 0 abstained
            self.w[n] *= float(np.exp(self.eta * reward)) * self.decay
        # renormalise to avoid drift/overflow
        s = sum(self.w.values()) or 1.0
        for n in self.names:
            self.w[n] = max(self.w[n] / s, 1e-6)

    def weights(self):
        s = sum(self.w.values()) or 1.0
        return {n: self.w[n] / s for n in self.names}
