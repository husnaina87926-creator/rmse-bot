"""Self-learning run (advisory). Re-mines edges, builds a candidate registry, and
runs champion-vs-challenger backtests. Writes an audit report + registry; does NOT
auto-edit the live strategy (promotion stays deliberate + forward-tested).

Run from project root:  python scripts/run_self_learning.py
"""
import sys
import os
import json
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmse_bot.config import load_config
from rmse_bot.data_feed import load_csv, fetch_dukascopy
from rmse_bot.self_learning import build_registry, candidate_rules, evaluate_challenger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_DIR = os.path.join(ROOT, "reports")
STATE_DIR = os.path.join(ROOT, "state")
HISTORY_DAYS = 400
MIN_COUNT = 200


def _get_data(sym, now, start):
    path = os.path.join(ROOT, "data", f"{sym}_15m.csv")
    if os.path.exists(path):
        return load_csv(path)
    return fetch_dukascopy(sym, "15m", start, now)


def main():
    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    now = dt.datetime.now(dt.timezone.utc)
    start = now - dt.timedelta(days=HISTORY_DAYS)
    date_str = now.strftime("%Y-%m-%d")

    md = [f"# RMSE_BOT Self-Learning Report — {date_str}\n",
          "_Advisory only. The bot records edges and tests them; it does NOT auto-change "
          "the live strategy. Promote a candidate only after forward-testing._\n"]
    registry_all = []
    promotions = []

    for sym in cfg["edge_rules"]:
        df = _get_data(sym, now, start)
        reg = build_registry(sym, df, cfg, min_count=MIN_COUNT)
        registry_all += reg
        held = sorted([r for r in reg if r["holds"]], key=lambda x: abs(x["net_oos"]), reverse=True)
        cands = candidate_rules(reg)

        md.append(f"\n## {sym}  ({len(df)} bars)\n")
        md.append(f"- OOS-held edges: **{len(held)}**  |  new candidates (not in strategy): **{len(cands)}**\n")
        md.append("\n**Robust edges (held out-of-sample):**\n")
        for r in held[:10]:
            tag = "IN-STRATEGY" if r["in_strategy"] else "NEW"
            md.append(f"  - `[{tag}]` {' & '.join(r['conditions'])} → {r['bias']} (OOS net {r['net_oos']:+.3f})\n")

        if cands:
            md.append("\n**Champion vs Challenger — would adding the new edge help?**\n")
            for c in sorted(cands, key=lambda x: abs(x["net_oos"]), reverse=True)[:8]:
                ev = evaluate_challenger(sym, df, cfg, c)
                mark = "✅ PROMOTE?" if ev["verdict"] == "PROMOTE-CANDIDATE" else "❌ reject"
                md.append(f"  - {mark} `+[{' & '.join(c['when'])}]`  "
                          f"champ ${ev['champ_return']} (PF {ev['champ_pf']}) → "
                          f"chall ${ev['chall_return']} (PF {ev['chall_pf']})\n")
                if ev["verdict"] == "PROMOTE-CANDIDATE":
                    promotions.append(ev)
        else:
            md.append("\n_No new robust candidates this run._\n")

    md.append(f"\n## Summary\n- Promotion candidates to forward-test: **{len(promotions)}**\n")
    for p in promotions:
        md.append(f"  - {p['symbol']}: add `{' & '.join(p['candidate'])}` "
                  f"({p['direction']}) — improves ${p['champ_return']}→${p['chall_return']}\n")

    os.makedirs(REPORTS_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, f"learning_{date_str}.md"), "w") as f:
        f.write("".join(md))
    with open(os.path.join(STATE_DIR, "candidate_registry.json"), "w") as f:
        json.dump({"date": date_str, "registry": registry_all,
                   "promotions": promotions}, f, indent=2)

    print("".join(md))


if __name__ == "__main__":
    main()
