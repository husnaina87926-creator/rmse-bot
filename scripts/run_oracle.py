"""ORACLE LAB runner — isolated crowd-flush forward experiment.

Every POLL_EVERY seconds: snapshot the crowd (funding/OI/long-short/taker via REST),
record it (building our own long history of Binance's 30-day-limited data), detect
flush events, and forward-paper-trade against them — self-grading live. A parallel
task records the true liquidation stream where the network allows.

FULLY ISOLATED: state/oracle/ only; never touches the champion bot. Run:
  python scripts/run_oracle.py            # continuous
  python scripts/run_oracle.py --once     # single cycle (test)
"""
import sys
import os
import asyncio
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.oracle_lab import (poll_positioning, record_snapshot, read_history,
                                 detect_events, oracle_step, record_liquidations, UNIVERSE)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
POLL_EVERY = 300          # 5 min


def one_cycle():
    now = dt.datetime.now(dt.timezone.utc)
    snap = poll_positioning(UNIVERSE)
    record_snapshot(STATE, snap)
    hist = read_history(STATE)
    events = detect_events(hist)
    summ = oracle_step(STATE, snap, events)
    ok = sum(1 for d in snap["symbols"].values() if "error" not in d)
    print(f"[oracle {now:%m-%d %H:%M:%S}] polled {ok}/{len(UNIVERSE)} | events={summ['new_events']} "
          f"| bal=${summ['balance']} open={summ['open']} closed={summ['closed']} "
          f"win={summ['win']}", flush=True)
    for ev in events:
        print(f"   FLUSH {ev['type']} {ev['symbol']} side={ev['side']} "
              f"d_px={ev.get('d_px')} d_oi={ev.get('d_oi')}", flush=True)
    return summ


async def liq_task():
    try:
        await record_liquidations(STATE)
    except Exception as e:
        print(f"[oracle] liq recorder: {e}", flush=True)


async def main():
    print(f"[oracle] LAB started — crowd-flush recorder + forward paper (isolated). "
          f"universe={len(UNIVERSE)} poll={POLL_EVERY}s", flush=True)
    loop = asyncio.get_running_loop()
    asyncio.ensure_future(liq_task())          # records liquidations where WS delivers
    while True:
        try:
            await loop.run_in_executor(None, one_cycle)
        except Exception as e:
            print(f"[oracle] cycle error: {e}", flush=True)
        await asyncio.sleep(POLL_EVERY)


if __name__ == "__main__":
    if "--once" in sys.argv:
        one_cycle()
    else:
        asyncio.run(main())
