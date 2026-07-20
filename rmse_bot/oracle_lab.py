"""ORACLE LAB — Binance-native CROWD-FLUSH engine (isolated forward experiment).

Philosophy (user's): don't predict price from indicators (proven dead) — instead
CATCH THE CROWD'S FORCED MOVES and take the other side. When over-leveraged traders
get liquidated or pile onto one side, the resulting forced move overshoots and
reverts. We record the positioning/flush data (which Binance keeps only ~30 days, or
not at all for liquidations) to build our OWN long history, detect flush events, and
forward-paper-trade against them — grading ourselves live.

FULLY ISOLATED: all state in state/oracle/, own paper account, NEVER touches the 14
champion accounts or their brain. Honest framing: real proof comes from live forward
deployment + time, not a backtest (the key data has no history) — exactly why we record.

Data planes:
  - REST (works from PK Mac + any VPS): funding, open interest, global/top long-short
    ratio, taker ratio, mark price, klines. -> positioning recorder + OI-cascade proxy.
  - Futures WS liquidation stream (needs a network where fstream delivers — the same
    non-US VPS real trading needs): true tick-level liquidations. Coded here; captures
    once run on a capable network (no-op where the WS data-plane is blocked).
"""
import json
import os
import urllib.request
import datetime as dt

from rmse_bot.atomic import atomic_json_dump

FAPI = "https://fapi.binance.com"
UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
            "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT"]
FEE = 0.0009               # futures taker round-trip (~0.045%/side)
START_BAL = 5000.0


def _get(ep, timeout=15):
    req = urllib.request.Request(FAPI + ep, headers={"User-Agent": "Mozilla/5.0 (RMSE_ORACLE)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


# ---------------- positioning recorder (REST — works now) ----------------

def poll_positioning(symbols=UNIVERSE):
    """One snapshot of the crowd's state per symbol. Fail-soft per symbol."""
    now = dt.datetime.now(dt.timezone.utc)
    snap = {"ts": now.isoformat(), "symbols": {}}
    for sym in symbols:
        try:
            prem = _get(f"/fapi/v1/premiumIndex?symbol={sym}")
            oi = _get(f"/fapi/v1/openInterest?symbol={sym}")
            gls = _get(f"/futures/data/globalLongShortAccountRatio?symbol={sym}&period=5m&limit=1")
            tls = _get(f"/futures/data/topLongShortPositionRatio?symbol={sym}&period=5m&limit=1")
            tkr = _get(f"/futures/data/takerlongshortRatio?symbol={sym}&period=5m&limit=1")
            snap["symbols"][sym] = {
                "mark": float(prem["markPrice"]),
                "funding": float(prem["lastFundingRate"]),
                "oi": float(oi["openInterest"]),
                "global_ls": float(gls[0]["longShortRatio"]) if gls else None,
                "top_ls": float(tls[0]["longShortRatio"]) if tls else None,
                "taker_ls": float(tkr[0]["buySellRatio"]) if tkr else None,
            }
        except Exception as e:
            snap["symbols"][sym] = {"error": str(e)[:80]}
    return snap


def record_snapshot(state_dir, snap):
    os.makedirs(os.path.join(state_dir, "oracle"), exist_ok=True)
    with open(os.path.join(state_dir, "oracle", "positioning.jsonl"), "a") as f:
        f.write(json.dumps(snap) + "\n")


def read_history(state_dir, keep=2000):
    p = os.path.join(state_dir, "oracle", "positioning.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out[-keep:]


# ---------------- flush-event detector (catch the crowd's forced moves) ----------------

def detect_events(history, oi_drop=0.03, price_move=0.01, funding_pctile=0.85):
    """Compare the two latest snapshots. A CROWD-FLUSH event fires when open interest
    de-leverages sharply AND price moves — the signature of a liquidation cascade —
    OR when funding is at a crowd-crowded extreme. We FADE it (take the other side of
    the forced move). Returns a list of event dicts. Needs >=2 snapshots per symbol."""
    if len(history) < 2:
        return []
    prev, cur = history[-2], history[-1]
    events = []
    for sym, c in cur.get("symbols", {}).items():
        p = prev.get("symbols", {}).get(sym)
        if not p or "error" in c or "error" in p:
            continue
        if not (c.get("oi") and p.get("oi") and c.get("mark") and p.get("mark")):
            continue
        d_oi = (c["oi"] - p["oi"]) / p["oi"]
        d_px = (c["mark"] - p["mark"]) / p["mark"]
        ev = None
        # OI-cascade (liquidation proxy): OI drops hard while price moves -> forced flush
        if d_oi <= -oi_drop and abs(d_px) >= price_move:
            # price fell => longs were flushed => fade LONG ; price spiked => fade SHORT
            ev = {"type": "oi_cascade", "symbol": sym, "d_oi": round(d_oi, 4),
                  "d_px": round(d_px, 4), "side": ("long" if d_px < 0 else "short"),
                  "mark": c["mark"]}
        # funding extreme (crowd crowded) — weaker; only as a same-direction confirmation
        elif c.get("funding") is not None:
            fr = c["funding"]
            if fr >= 0.0005 and d_px >= price_move:   # crowded longs + up spike -> fade short
                ev = {"type": "funding_extreme", "symbol": sym, "funding": fr,
                      "d_px": round(d_px, 4), "side": "short", "mark": c["mark"]}
            elif fr <= -0.0005 and d_px <= -price_move:
                ev = {"type": "funding_extreme", "symbol": sym, "funding": fr,
                      "d_px": round(d_px, 4), "side": "long", "mark": c["mark"]}
        if ev:
            ev["ts"] = cur["ts"]
            events.append(ev)
    return events


# ---------------- isolated forward paper trader + self-grading ----------------

def _load_oracle_state(state_dir):
    p = os.path.join(state_dir, "oracle", "account.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": START_BAL, "open": [], "closed": []}


def oracle_step(state_dir, snap, events, hold_min=240, tp=0.02, sl=0.012):
    """Manage open paper positions against the latest marks, then open new ones on fresh
    flush events (one per symbol at a time), EV-gated. All isolated. Returns a summary."""
    st = _load_oracle_state(state_dir)
    now = dt.datetime.fromisoformat(snap["ts"])
    marks = {s: d.get("mark") for s, d in snap.get("symbols", {}).items() if d.get("mark")}
    # manage opens
    still = []
    for pos in st["open"]:
        m = marks.get(pos["symbol"])
        if m is None:
            still.append(pos); continue
        mv = (m - pos["entry"]) / pos["entry"] * (1 if pos["side"] == "long" else -1)
        age = (now - dt.datetime.fromisoformat(pos["open_ts"])).total_seconds() / 60
        outcome = None
        if mv >= tp: outcome = "tp"
        elif mv <= -sl: outcome = "sl"
        elif age >= hold_min: outcome = "time"
        if outcome:
            pnl = (mv - FEE) * pos["risk_usd"] / sl    # position sized to risk_usd at SL
            st["balance"] += pnl
            st["closed"].append({**pos, "exit": m, "outcome": outcome,
                                 "pnl": round(pnl, 2), "close_ts": snap["ts"],
                                 "ret": round(mv, 4)})
        else:
            still.append(pos)
    st["open"] = still
    open_syms = {p["symbol"] for p in st["open"]}
    # open new on fresh events (EV-gate: expected fade move must beat fee+buffer)
    for ev in events:
        if ev["symbol"] in open_syms:
            continue
        # expected fade edge (heuristic): revert a fraction of the forced move; must beat cost
        exp_edge = abs(ev.get("d_px", 0)) * 0.5
        if exp_edge - FEE - 0.002 <= 0:
            continue
        st["open"].append({"symbol": ev["symbol"], "side": ev["side"], "entry": ev["mark"],
                           "open_ts": ev["ts"], "trigger": ev["type"],
                           "risk_usd": 50.0})
        open_syms.add(ev["symbol"])
    atomic_json_dump(st, os.path.join(state_dir, "oracle", "account.json"))
    wins = [t for t in st["closed"] if t["pnl"] > 0]
    return {"balance": round(st["balance"], 2), "open": len(st["open"]),
            "closed": len(st["closed"]),
            "win": round(len(wins) / len(st["closed"]), 2) if st["closed"] else None,
            "new_events": len(events)}


# ---------------- liquidation WS recorder (needs capable network; no-op if blocked) ----------------

async def record_liquidations(state_dir, seconds=None):
    """Record the true tick-level liquidation stream. Runs on a network where the
    Futures WS data-plane delivers (the non-US VPS). Where blocked (PK Mac / US VPS)
    it connects but receives nothing — harmless. Appends to oracle/liquidations.jsonl."""
    import asyncio
    import websockets
    url = "wss://fstream.binance.com/ws/!forceOrder@arr"
    path = os.path.join(state_dir, "oracle", "liquidations.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    import time as _t
    t0 = _t.time()
    while True:
        try:
            async with websockets.connect(url, ping_interval=15, ping_timeout=20) as ws:
                async for raw in ws:
                    o = json.loads(raw).get("o", {})
                    if not o:
                        continue
                    rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(),
                           "symbol": o.get("s"), "side": o.get("S"),
                           "qty": float(o.get("q", 0)), "price": float(o.get("p", 0)),
                           "usd": float(o.get("q", 0)) * float(o.get("p", 0))}
                    with open(path, "a") as f:
                        f.write(json.dumps(rec) + "\n")
                    if seconds and _t.time() - t0 > seconds:
                        return
        except Exception:
            await asyncio.sleep(5)
            if seconds and _t.time() - t0 > seconds:
                return
