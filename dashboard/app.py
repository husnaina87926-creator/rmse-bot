"""RMSE_BOT dashboard (Streamlit, free).

Reads the bot's live state straight from the GitHub repo (raw files, always fresh),
so it shows the same data the 24/7 bot is committing every ~15 min. Falls back to
local files when run locally.

Deploy free at share.streamlit.io -> repo husnaina87926-creator/rmse-bot,
branch main, file dashboard/app.py.
Run locally:  streamlit run dashboard/app.py
"""
import json
import urllib.request

import pandas as pd
import streamlit as st

RAW = "https://raw.githubusercontent.com/husnaina87926-creator/rmse-bot/main"
START_BAL = 100.0


@st.cache_data(ttl=120)
def load_json(path):
    try:
        req = urllib.request.Request(f"{RAW}/{path}", headers={"User-Agent": "rmse-dash"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return None


def stats(state):
    closed = (state or {}).get("closed", [])
    wins = [t for t in closed if t["pnl"] > 0]
    wr = len(wins) / len(closed) if closed else 0.0
    pnl = sum(t["pnl"] for t in closed)
    return {"balance": (state or {}).get("balance", START_BAL), "trades": len(closed),
            "open": len((state or {}).get("open", [])), "win": wr, "pnl": pnl}


st.set_page_config(page_title="RMSE_BOT", page_icon="🤖", layout="wide")
st.title("🤖 RMSE_BOT — Gold Trading Bot")
st.caption("Live paper-trading (virtual $). Data auto-updates from GitHub every ~15 min.")
if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

champ = load_json("state/paper_state.json")
if not champ:
    st.warning("State load nahi hua. Thori dair baad refresh karein.")
    st.stop()

s = stats(champ)
c1, c2, c3, c4 = st.columns(4)
c1.metric("💰 Balance", f"${s['balance']:.2f}", f"{s['balance']-START_BAL:+.2f}")
c2.metric("📊 Trades", s["trades"])
c3.metric("🎯 Win rate", f"{s['win']:.0%}")
c4.metric("📈 Total P&L", f"${s['pnl']:.2f}")

# Equity curve from closed-trade balances
closed = champ.get("closed", [])
if closed:
    eq = pd.DataFrame({"balance": [START_BAL] + [t["balance_after"] for t in closed]})
    st.subheader("📈 Equity curve")
    st.line_chart(eq, y="balance", height=240)

col_l, col_r = st.columns(2)
with col_l:
    st.subheader("🟢 Open trades")
    op = champ.get("open", [])
    if op:
        st.dataframe(pd.DataFrame([{
            "Symbol": p["symbol"], "Dir": p["direction"].upper(),
            "Entry": round(p["entry"], 2), "SL": round(p["sl"], 2),
            "TP": round(p["tp"], 2), "Since": p["open_time"][:16],
        } for p in op]), hide_index=True, use_container_width=True)
    else:
        st.info("Abhi koi trade khuli nahi.")

with col_r:
    st.subheader("✅ Recent closed trades")
    if closed:
        st.dataframe(pd.DataFrame([{
            "Symbol": t["symbol"], "Dir": t["direction"].upper(),
            "Result": t["outcome"].upper(), "P&L $": round(t["pnl"], 2),
            "Closed": t["close_time"][:16],
        } for t in reversed(closed[-12:])]), hide_index=True, use_container_width=True)
    else:
        st.info("Abhi koi trade band nahi hui.")

# Champion vs challengers
st.subheader("🏆 Champion vs Challengers (forward test)")
rows = [{"Account": "champion", **{k: v for k, v in stats(champ).items()}}]
for i in (1, 2, 3):
    ch = load_json(f"state/challenger_{i}.json")
    if ch:
        rows.append({"Account": f"challenger_{i}", **stats(ch)})
cmp = pd.DataFrame(rows)
cmp = cmp.rename(columns={"balance": "Balance$", "trades": "Trades", "open": "Open",
                          "win": "Win", "pnl": "P&L$"})
cmp["Win"] = (cmp["Win"] * 100).round(0).astype(int).astype(str) + "%"
cmp["Balance$"] = cmp["Balance$"].round(2)
cmp["P&L$"] = cmp["P&L$"].round(2)
st.dataframe(cmp, hide_index=True, use_container_width=True)

# Strategy leaderboard
lb = load_json("state/strategy_leaderboard.json")
if lb and lb.get("board"):
    st.subheader("🧪 Strategy Lab leaderboard (bot-generated, by robust profit)")
    for sym, items in lb["board"].items():
        st.caption(f"{sym} — top bot-found strategies (backtest; forward-test before trusting)")
        st.dataframe(pd.DataFrame([{
            "Score": x["score"], "Return$": x["return"], "PF": x["pf"],
            "Win": f"{x['win']*100:.0f}%", "MaxDD$": x["maxdd"],
            "Consist": f"{x['consistency']*100:.0f}%",
            "Strategy": f"{x['direction']} [{' & '.join(x['entry'])}] rr{x['exit']['rr']}/be{x['exit']['be']}",
        } for x in items[:8]]), hide_index=True, use_container_width=True)

st.caption("⚠️ Paper trading only — virtual money. Past results ≠ future. Not financial advice.")
