"""RMSE_BOT dashboard — futuristic, mobile-first (Streamlit).

Reads live state from the GitHub repo (raw files, always fresh; local fallback), so it
mirrors what the 24/7 bot commits every ~15 min.
Deploy: share.streamlit.io -> repo husnaina87926-creator/rmse-bot, branch main,
file dashboard/app.py.  Local: streamlit run dashboard/app.py
"""
import json
import urllib.request

import pandas as pd
import altair as alt
import streamlit as st

RAW = "https://raw.githubusercontent.com/husnaina87926-creator/rmse-bot/main"
START_BAL = 100.0
CYAN, PURPLE, GREEN, RED = "#00e5ff", "#a855f7", "#00ffa3", "#ff4d6d"

st.set_page_config(page_title="RMSE_BOT", page_icon="🤖", layout="wide",
                   initial_sidebar_state="collapsed")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Rajdhani:wght@500;600;700&display=swap');
#MainMenu, header, footer {visibility:hidden;}
.stApp { background:
   radial-gradient(1200px 600px at 15% -10%, rgba(0,229,255,0.10), transparent 60%),
   radial-gradient(1000px 500px at 95% 0%, rgba(168,85,247,0.12), transparent 55%),
   #070b14 fixed;
   color:#e6edf7; font-family:'Rajdhani',sans-serif; }
.block-container { padding-top:1.2rem; max-width:1200px; }
h1,h2,h3 { font-family:'Orbitron',sans-serif !important; letter-spacing:1px; }
.hero { font-family:'Orbitron'; font-size:2rem; font-weight:800;
   background:linear-gradient(90deg,#00e5ff,#a855f7); -webkit-background-clip:text;
   -webkit-text-fill-color:transparent; margin-bottom:2px; }
.sub { color:#7d8db0; font-size:0.95rem; margin-bottom:14px; }
.sect { font-family:'Orbitron'; font-size:1.05rem; margin:22px 0 10px; color:#cfe9ff;
   border-left:3px solid #00e5ff; padding-left:10px; text-shadow:0 0 12px rgba(0,229,255,0.4); }
.kpi-grid { display:flex; flex-wrap:wrap; gap:14px; }
.kpi { flex:1 1 150px; background:rgba(255,255,255,0.035); backdrop-filter:blur(10px);
   border:1px solid rgba(0,229,255,0.18); border-radius:16px; padding:16px 18px;
   box-shadow:0 0 22px rgba(0,229,255,0.07), inset 0 0 20px rgba(0,229,255,0.03); }
.kpi-t { font-size:0.82rem; color:#8aa0c6; text-transform:uppercase; letter-spacing:1px; }
.kpi-v { font-family:'Orbitron'; font-size:1.75rem; font-weight:800; margin-top:4px;
   text-shadow:0 0 18px currentColor; }
.kpi-s { font-size:0.85rem; color:#7d8db0; margin-top:2px; }
.tbl-wrap { overflow-x:auto; border-radius:14px; border:1px solid rgba(255,255,255,0.07);
   background:rgba(255,255,255,0.025); backdrop-filter:blur(8px); }
table.ft { width:100%; border-collapse:collapse; font-size:0.92rem; min-width:480px; }
table.ft th { text-align:left; padding:10px 12px; color:#9fb3d6; font-weight:700;
   text-transform:uppercase; font-size:0.72rem; letter-spacing:1px;
   border-bottom:1px solid rgba(255,255,255,0.08); }
table.ft td { padding:9px 12px; border-bottom:1px solid rgba(255,255,255,0.05); }
table.ft tr:hover td { background:rgba(0,229,255,0.05); }
.pos { color:#00ffa3; font-weight:700; } .neg { color:#ff4d6d; font-weight:700; }
.pill { padding:2px 9px; border-radius:999px; font-size:0.74rem; font-weight:700; }
.pill.buy { background:rgba(0,255,163,0.13); color:#00ffa3; }
.pill.sell { background:rgba(255,77,109,0.13); color:#ff4d6d; }
.pill.tp { background:rgba(0,255,163,0.13); color:#00ffa3; }
.pill.sl,.pill.loss { background:rgba(255,77,109,0.13); color:#ff4d6d; }
.pill.time,.pill.win { background:rgba(0,229,255,0.12); color:#00e5ff; }
.stButton>button { background:rgba(0,229,255,0.1); color:#00e5ff; border:1px solid rgba(0,229,255,0.35);
   border-radius:10px; font-family:'Orbitron'; font-size:0.8rem; }
.foot { color:#5d6b88; font-size:0.8rem; margin-top:24px; }
@media (max-width:640px){ .hero{font-size:1.5rem;} .kpi-v{font-size:1.4rem;} .block-container{padding:0.6rem;} }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


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
    return {"balance": (state or {}).get("balance", START_BAL), "trades": len(closed),
            "open": len((state or {}).get("open", [])),
            "win": (len(wins) / len(closed) if closed else 0.0),
            "pnl": sum(t["pnl"] for t in closed)}


def money(x):
    cls = "pos" if x >= 0 else "neg"
    return f'<span class="{cls}">${x:+.2f}</span>'


def table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table class="ft"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


# ---------- Header ----------
st.markdown('<div class="hero">⚡ RMSE&nbsp;BOT</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Autonomous gold trading bot · live paper-trade · self-learning</div>',
            unsafe_allow_html=True)
if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

champ = load_json("state/paper_state.json")
if not champ:
    st.warning("State load nahi hua — thori dair baad Refresh karein.")
    st.stop()
s = stats(champ)

# ---------- KPIs ----------
bal_c = GREEN if s["balance"] >= START_BAL else RED
pnl_c = GREEN if s["pnl"] >= 0 else RED
kpis = [
    ("Balance", f"${s['balance']:.2f}", f"{s['balance']-START_BAL:+.2f} from $100", bal_c),
    ("Total P&L", f"${s['pnl']:+.2f}", "realized", pnl_c),
    ("Trades", f"{s['trades']}", f"{s['open']} open now", CYAN),
    ("Win rate", f"{s['win']*100:.0f}%", "of closed", PURPLE),
]
cards = "".join(
    f'<div class="kpi"><div class="kpi-t">{t}</div>'
    f'<div class="kpi-v" style="color:{c}">{v}</div><div class="kpi-s">{sb}</div></div>'
    for t, v, sb, c in kpis)
st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)

# ---------- Equity curve ----------
closed = champ.get("closed", [])
if closed:
    st.markdown('<div class="sect">📈 Equity Curve</div>', unsafe_allow_html=True)
    eq = pd.DataFrame({"#": list(range(len(closed) + 1)),
                       "Balance": [START_BAL] + [t["balance_after"] for t in closed]})
    chart = alt.Chart(eq).mark_area(
        line={"color": CYAN, "strokeWidth": 2.5},
        color=alt.Gradient(gradient="linear",
                           stops=[alt.GradientStop(color="rgba(0,229,255,0.30)", offset=0),
                                  alt.GradientStop(color="rgba(0,229,255,0)", offset=1)],
                           x1=1, x2=1, y1=1, y2=0)
    ).encode(
        x=alt.X("#:Q", title=None, axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False)),
        y=alt.Y("Balance:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(grid=True, gridColor="rgba(255,255,255,0.06)", domain=False, tickColor="rgba(0,0,0,0)")),
    ).properties(height=230).configure_view(strokeWidth=0).configure(background="rgba(0,0,0,0)")
    st.altair_chart(chart, use_container_width=True)

# ---------- Open trades ----------
st.markdown('<div class="sect">🟢 Open Trades</div>', unsafe_allow_html=True)
op = champ.get("open", [])
if op:
    rows = [[p["symbol"], f'<span class="pill {p["direction"]}">{p["direction"].upper()}</span>',
             f'{p["entry"]:.2f}', f'{p["sl"]:.2f}', f'{p["tp"]:.2f}', p["open_time"][:16]] for p in op]
    st.markdown(table(["Symbol", "Dir", "Entry", "SL", "TP", "Opened"], rows), unsafe_allow_html=True)
else:
    st.markdown('<div class="sub">Abhi koi trade khuli nahi — bot intezar mein hai.</div>', unsafe_allow_html=True)

# ---------- Closed trades ----------
st.markdown('<div class="sect">✅ Recent Closed Trades</div>', unsafe_allow_html=True)
if closed:
    rows = [[t["symbol"], f'<span class="pill {t["direction"]}">{t["direction"].upper()}</span>',
             f'<span class="pill {t["outcome"]}">{t["outcome"].upper()}</span>',
             money(t["pnl"]), t["close_time"][:16]] for t in reversed(closed[-12:])]
    st.markdown(table(["Symbol", "Dir", "Result", "P&L", "Closed"], rows), unsafe_allow_html=True)
else:
    st.markdown('<div class="sub">Abhi koi trade band nahi hui.</div>', unsafe_allow_html=True)

# ---------- Champion vs challengers ----------
st.markdown('<div class="sect">🏆 Champion vs Challengers</div>', unsafe_allow_html=True)
accs = [("champion", champ)]
for i in (1, 2, 3):
    ch = load_json(f"state/challenger_{i}.json")
    if ch:
        accs.append((f"challenger {i}", ch))
rows = []
for name, stt in accs:
    a = stats(stt)
    rows.append([name, f'${a["balance"]:.2f}', a["trades"], money(a["pnl"]), f'{a["win"]*100:.0f}%'])
st.markdown(table(["Account", "Balance", "Trades", "P&L", "Win"], rows), unsafe_allow_html=True)

# ---------- Strategy leaderboard ----------
lb = load_json("state/strategy_leaderboard.json")
if lb and lb.get("board"):
    st.markdown('<div class="sect">🧪 Strategy Lab — Bot-Found Strategies</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Ranked by robust profit (backtest). Top = candidate, forward-test before trusting.</div>',
                unsafe_allow_html=True)
    for sym, items in lb["board"].items():
        rows = [[i + 1, f'<b style="color:{CYAN}">{x["score"]:.0f}</b>', money(x["return"]),
                 f'{x["pf"]:.2f}', f'{x["win"]*100:.0f}%', f'{x["consistency"]*100:.0f}%',
                 f'{x["direction"]} [{" & ".join(x["entry"])}] rr{x["exit"]["rr"]}']
                for i, x in enumerate(items[:8])]
        st.markdown(table(["#", "Score", "Return", "PF", "Win", "Consist", "Strategy"], rows),
                    unsafe_allow_html=True)

st.markdown('<div class="foot">⚠️ Paper trading (virtual money). Past results ≠ future. Not financial advice. '
            'Data: GitHub · auto-updates ~15 min.</div>', unsafe_allow_html=True)
