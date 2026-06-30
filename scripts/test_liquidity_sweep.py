"""Liquidity-sweep strategy lab on BTC 3-min.

Concept: stops cluster just beyond recent swing highs (buy-side liq) / swing lows
(sell-side liq). Price tends to "sweep" them (wick beyond) then either REVERSE
(fade) or CONTINUE (break & go). We build many variations of this ONE concept and
backtest each with realistic Binance fees. Honest: 3m = many trades = heavy fee drag.

Variations tested (structural):
  R = Sweep-Reversal (fade the sweep)      C = Sweep-Continuation (follow the break)
  exit: OL = opposite-liquidity   RR = fixed reward:risk
  dir: L/S/both    swing lookback N    optional trend filter
Run: python scripts/test_liquidity_sweep.py
"""
import sys, os, datetime as dt
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rmse_bot.binance_feed import fetch_binance_klines

SYM = "BTCUSDT"
COST = 0.0005          # 0.05% per side (Binance taker ~0.04% + slippage) -> ~0.10% round
RISK = 0.01            # 1% risk/trade (3m high-freq; 10% would blow up instantly)
START = 5000.0
MAX_HOLD = 100         # bars (5h on 3m)
LEVERAGE = 20          # cap position notional (realistic; tight 3m stops else demand 200x)


def signals(o, h, l, c, N, kind, direction):
    """Yield (i, dir, entry, sl, tp_level_kind). kind: 'R' reversal / 'C' continuation."""
    n = len(c)
    out = []
    for i in range(N, n - 1):
        ph = h[i - N:i].max()      # prior-N swing high = buy-side liquidity
        pl = l[i - N:i].min()      # prior-N swing low  = sell-side liquidity
        if kind == "R":
            # sweep below low then close back above -> reversal LONG
            if direction in ("L", "both") and l[i] < pl and c[i] > pl:
                out.append((i, "buy", c[i], l[i], ph))      # tp target = opposite liq (ph)
            # sweep above high then close back below -> reversal SHORT
            if direction in ("S", "both") and h[i] > ph and c[i] < ph:
                out.append((i, "sell", c[i], h[i], pl))
        else:  # continuation: close beyond the swept level, follow the break
            if direction in ("L", "both") and c[i] > ph and c[i - 1] <= ph:
                out.append((i, "buy", c[i], pl, ph))        # sl = opposite (pl)
            if direction in ("S", "both") and c[i] < pl and c[i - 1] >= pl:
                out.append((i, "sell", c[i], ph, pl))
    return out


def run(o, h, l, c, sig, exit_mode, rr=2.0, trend=None):
    bal = START
    trades = []
    last_close_i = -1
    for (i, d, entry, slv, oppliq) in sig:
        if i <= last_close_i:
            continue                      # no overlapping trades
        if trend is not None:
            if d == "buy" and not trend[i]:
                continue
            if d == "sell" and trend[i]:
                continue
        risk_per = abs(entry - slv)
        if risk_per <= 0:
            continue
        if exit_mode == "OL":
            tp = oppliq
            if (d == "buy" and tp <= entry) or (d == "sell" and tp >= entry):
                continue                  # opposite liq not beyond entry
        else:                              # fixed RR
            tp = entry + rr * risk_per if d == "buy" else entry - rr * risk_per
        units = min((bal * RISK) / risk_per, (bal * LEVERAGE) / entry)   # cap at LEVERAGE
        outcome, exitp, ci = "time", c[min(i + MAX_HOLD, len(c) - 1)], min(i + MAX_HOLD, len(c) - 1)
        for j in range(i + 1, min(i + 1 + MAX_HOLD, len(c))):
            if d == "buy":
                if l[j] <= slv: outcome, exitp, ci = "sl", slv, j; break
                if h[j] >= tp: outcome, exitp, ci = "tp", tp, j; break
            else:
                if h[j] >= slv: outcome, exitp, ci = "sl", slv, j; break
                if l[j] <= tp: outcome, exitp, ci = "tp", tp, j; break
        move = (exitp - entry) if d == "buy" else (entry - exitp)
        pnl = move * units - (entry + exitp) * units * COST
        bal += pnl
        trades.append(pnl)
        last_close_i = ci
        if bal <= 0:
            break
    if not trades:
        return None
    wins = sum(1 for t in trades if t > 0)
    return {"n": len(trades), "win": wins / len(trades), "final": bal,
            "ret": bal - START, "avg": np.mean(trades)}


def main():
    now = dt.datetime.now(dt.timezone.utc)
    TF = sys.argv[1] if len(sys.argv) > 1 else "3m"
    DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    df = fetch_binance_klines(SYM, TF, now - dt.timedelta(days=DAYS), now)
    o, h, l, c = (df[x].values for x in ("open", "high", "low", "close"))
    days = (df["time"].iloc[-1] - df["time"].iloc[0]).days
    ema200 = df["close"].ewm(span=200, adjust=False).mean().values
    trend_up = c > ema200
    print(f"{SYM} {TF}: {len(df)} bars, {days} days, cost {COST*100:.2f}%/side, risk {RISK*100:.0f}%/trade\n")
    print(f"{'#':<3}{'strategy':<40}{'trades':>7}{'win%':>6}{'final$':>10}{'P&L':>9}{'avg$':>8}")
    configs = [
        ("R both N10, exit opposite-liq", "R", "both", 10, "OL", 2.0, None),
        ("R both N20, exit opposite-liq", "R", "both", 20, "OL", 2.0, None),
        ("R LONG only N10, opp-liq", "R", "L", 10, "OL", 2.0, None),
        ("R SHORT only N10, opp-liq", "R", "S", 10, "OL", 2.0, None),
        ("R both N10, fixed RR2", "R", "both", 10, "RR", 2.0, None),
        ("R both N10, fixed RR1", "R", "both", 10, "RR", 1.0, None),
        ("R both N10, RR2 + trend filter", "R", "both", 10, "RR", 2.0, trend_up),
        ("C both N10, exit opposite-liq", "C", "both", 10, "OL", 2.0, None),
        ("C both N20, fixed RR2", "C", "both", 20, "RR", 2.0, None),
        ("C both N10, RR2 + trend filter", "C", "both", 10, "RR", 2.0, trend_up),
    ]
    pos = 0
    for k, (name, kind, d, N, em, rr, tr) in enumerate(configs, 1):
        sig = signals(o, h, l, c, N, kind, d)
        r = run(o, h, l, c, sig, em, rr, tr)
        if r is None:
            print(f"{k:<3}{name:<40}{'(no trades)':>7}"); continue
        flag = "POS" if r["ret"] > 0 else "neg"
        if r["ret"] > 0: pos += 1
        print(f"{k:<3}{name:<40}{r['n']:>7}{r['win']*100:>5.0f}%{r['final']:>10.0f}{r['ret']:>+9.0f}{r['avg']:>+8.2f}  [{flag}]")
    print(f"\n=> {len(configs)} strategies tested, {pos} positive after fees")


if __name__ == "__main__":
    main()
