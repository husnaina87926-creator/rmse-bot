"""RMSE_BOT dashboard — futuristic, mobile-first, multi-account (Streamlit).

Shows 3 independent paper accounts (gold, BTC, ETH), each $5000, plus a combined total.
Reads live state from the GitHub repo (raw, always fresh; local fallback).
Deploy: share.streamlit.io -> repo husnaina87926-creator/rmse-bot, branch main, file dashboard/app.py
"""
import json
import urllib.request

import pandas as pd
import altair as alt
import streamlit as st

RAW = "https://raw.githubusercontent.com/husnaina87926-creator/rmse-bot/main"
START = 5000.0
CYAN, PURPLE, GREEN, RED, GOLD = "#00e5ff", "#a855f7", "#00ffa3", "#ff4d6d", "#ffd24a"
ACCOUNTS = [("gold", "🥇 Gold", GOLD), ("btc", "₿ BTC", "#f7931a"), ("eth", "⟠ ETH", "#8a92b2")]

st.set_page_config(page_title="RMSE_BOT", page_icon="🤖", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Rajdhani:wght@500;600;700&display=swap');
#MainMenu, header, footer {visibility:hidden;}
.stApp { background:
   radial-gradient(1200px 600px at 15% -10%, rgba(0,229,255,0.10), transparent 60%),
   radial-gradient(1000px 500px at 95% 0%, rgba(168,85,247,0.12), transparent 55%), #070b14 fixed;
   color:#e6edf7; font-family:'Rajdhani',sans-serif; }
.block-container { padding-top:1rem; max-width:1180px; }
h1,h2,h3 { font-family:'Orbitron',sans-serif !important; letter-spacing:1px; }
.hero { font-family:'Orbitron'; font-size:1.9rem; font-weight:800;
   background:linear-gradient(90deg,#00e5ff,#a855f7); -webkit-background-clip:text;
   -webkit-text-fill-color:transparent; }
.sub { color:#7d8db0; font-size:0.9rem; margin-bottom:12px; }
.sect { font-family:'Orbitron'; font-size:1rem; margin:20px 0 10px; color:#cfe9ff;
   border-left:3px solid #00e5ff; padding-left:10px; }
.kpi-grid { display:flex; flex-wrap:wrap; gap:14px; }
.kpi { flex:1 1 150px; background:rgba(255,255,255,0.035); backdrop-filter:blur(10px);
   border:1px solid rgba(0,229,255,0.18); border-radius:16px; padding:16px 18px;
   box-shadow:0 0 22px rgba(0,229,255,0.07); }
.kpi-t { font-size:0.78rem; color:#8aa0c6; text-transform:uppercase; letter-spacing:1px; }
.kpi-v { font-family:'Orbitron'; font-size:1.6rem; font-weight:800; margin-top:4px; text-shadow:0 0 18px currentColor; }
.kpi-s { font-size:0.82rem; color:#7d8db0; margin-top:2px; }
.acard { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08);
   border-radius:14px; padding:14px 16px; }
.acard .nm { font-family:'Orbitron'; font-size:1rem; }
.acard .bal { font-family:'Orbitron'; font-size:1.5rem; font-weight:800; margin-top:6px; }
.tbl-wrap { overflow-x:auto; border-radius:14px; border:1px solid rgba(255,255,255,0.07);
   background:rgba(255,255,255,0.025); }
table.ft { width:100%; border-collapse:collapse; font-size:0.9rem; min-width:440px; }
table.ft th { text-align:left; padding:9px 12px; color:#9fb3d6; font-weight:700;
   text-transform:uppercase; font-size:0.7rem; border-bottom:1px solid rgba(255,255,255,0.08); }
table.ft td { padding:8px 12px; border-bottom:1px solid rgba(255,255,255,0.05); }
.pos { color:#00ffa3; font-weight:700; } .neg { color:#ff4d6d; font-weight:700; }
.pill { padding:2px 9px; border-radius:999px; font-size:0.72rem; font-weight:700; }
.pill.buy,.pill.tp,.pill.win { background:rgba(0,255,163,0.13); color:#00ffa3; }
.pill.sell { background:rgba(255,210,74,0.14); color:#ffd24a; }
.pill.sl,.pill.loss { background:rgba(255,77,109,0.13); color:#ff4d6d; }
.pill.time { background:rgba(0,229,255,0.12); color:#00e5ff; }
.stButton>button { background:rgba(0,229,255,0.1); color:#00e5ff; border:1px solid rgba(0,229,255,0.35);
   border-radius:10px; font-family:'Orbitron'; font-size:0.78rem; }
.stTabs [data-baseweb="tab"] { font-family:'Orbitron'; }
.foot { color:#5d6b88; font-size:0.78rem; margin-top:22px; }
@media (max-width:640px){ .hero{font-size:1.45rem;} .kpi-v{font-size:1.3rem;} .block-container{padding:0.6rem;} }
</style>
""", unsafe_allow_html=True)


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


def stats(s):
    closed = (s or {}).get("closed", [])
    wins = [t for t in closed if t["pnl"] > 0]
    return {"balance": (s or {}).get("balance", START), "trades": len(closed),
            "open": len((s or {}).get("open", [])),
            "win": (len(wins) / len(closed) if closed else 0.0),
            "pnl": sum(t["pnl"] for t in closed)}


def money(x):
    return f'<span class="{"pos" if x >= 0 else "neg"}">${x:+,.2f}</span>'


def table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table class="ft"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


# ---------- load ----------
states = {k: load_json(f"state/{k}.json") for k, _, _ in ACCOUNTS}

st.markdown('<div class="hero">⚡ RMSE&nbsp;BOT</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">3 autonomous paper accounts · gold (long) + BTC/ETH (all-weather) · live forward-test</div>',
            unsafe_allow_html=True)
if st.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

if not any(states.values()):
    st.warning("State load nahi hua — thori dair baad Refresh karein.")
    st.stop()

# ---------- combined KPIs ----------
total_bal = sum(stats(states[k])["balance"] for k, _, _ in ACCOUNTS)
total_pnl = sum(stats(states[k])["pnl"] for k, _, _ in ACCOUNTS)
total_trades = sum(stats(states[k])["trades"] for k, _, _ in ACCOUNTS)
total_open = sum(stats(states[k])["open"] for k, _, _ in ACCOUNTS)
start_total = START * len(ACCOUNTS)
pnl_c = GREEN if total_pnl >= 0 else RED
kpis = [("Total Balance", f"${total_bal:,.0f}", f"{total_bal-start_total:+,.0f} from ${start_total:,.0f}",
         GREEN if total_bal >= start_total else RED),
        ("Total P&L", f"${total_pnl:+,.0f}", "realized (3 accounts)", pnl_c),
        ("Total Trades", f"{total_trades}", f"{total_open} open now", CYAN),
        ("Accounts", "3", "gold · BTC · ETH", PURPLE)]
st.markdown('<div class="kpi-grid">' + "".join(
    f'<div class="kpi"><div class="kpi-t">{t}</div><div class="kpi-v" style="color:{c}">{v}</div>'
    f'<div class="kpi-s">{sb}</div></div>' for t, v, sb, c in kpis) + '</div>', unsafe_allow_html=True)

# ---------- per-account quick cards ----------
st.markdown('<div class="sect">📂 Accounts</div>', unsafe_allow_html=True)
cols = st.columns(len(ACCOUNTS))
for col, (k, label, color) in zip(cols, ACCOUNTS):
    a = stats(states[k])
    bcol = GREEN if a["balance"] >= START else RED
    col.markdown(
        f'<div class="acard"><div class="nm" style="color:{color}">{label}</div>'
        f'<div class="bal" style="color:{bcol}">${a["balance"]:,.0f}</div>'
        f'<div class="kpi-s">P&L {money(a["pnl"])} · {a["trades"]} trades · win {a["win"]*100:.0f}% · {a["open"]} open</div></div>',
        unsafe_allow_html=True)

# ---------- per-account detail tabs ----------
tabs = st.tabs([label for _, label, _ in ACCOUNTS])
for tab, (k, label, color) in zip(tabs, ACCOUNTS):
    with tab:
        s = states[k]
        if not s:
            st.info("Is account ka data abhi nahi.")
            continue
        closed = s.get("closed", [])
        if closed:
            eq = pd.DataFrame({"#": range(len(closed) + 1),
                               "Balance": [START] + [t["balance_after"] for t in closed]})
            ch = alt.Chart(eq).mark_area(
                line={"color": color, "strokeWidth": 2.5},
                color=alt.Gradient(gradient="linear",
                    stops=[alt.GradientStop(color=color, offset=0),
                           alt.GradientStop(color="rgba(0,0,0,0)", offset=1)], x1=1, x2=1, y1=1, y2=0)
            ).encode(
                x=alt.X("#:Q", title=None, axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False)),
                y=alt.Y("Balance:Q", title=None, scale=alt.Scale(zero=False),
                        axis=alt.Axis(grid=True, gridColor="rgba(255,255,255,0.06)", domain=False)),
            ).properties(height=220).configure_view(strokeWidth=0).configure(background="rgba(0,0,0,0)")
            st.altair_chart(ch, use_container_width=True)
        op = s.get("open", [])
        if op:
            st.markdown(table(["Symbol", "Dir", "Entry", "SL", "TP", "Opened"],
                [[p["symbol"], f'<span class="pill {p["direction"]}">{p["direction"].upper()}</span>',
                  f'{p["entry"]:,.2f}', f'{p["sl"]:,.2f}', f'{p["tp"]:,.2f}', p["open_time"][:16]] for p in op]),
                unsafe_allow_html=True)
        if closed:
            st.markdown(table(["Symbol", "Dir", "Result", "P&L", "Closed"],
                [[t["symbol"], f'<span class="pill {t["direction"]}">{t["direction"].upper()}</span>',
                  f'<span class="pill {t["outcome"]}">{t["outcome"].upper()}</span>', money(t["pnl"]),
                  t["close_time"][:16]] for t in reversed(closed[-12:])]), unsafe_allow_html=True)
        elif not op:
            st.markdown('<div class="sub">Abhi koi trade nahi — bot sahi mauqe ka intezar mein.</div>',
                        unsafe_allow_html=True)

st.markdown('<div class="foot">⚠️ Paper trading (virtual $5000/account). Past ≠ future. Not financial advice. '
            'Data: GitHub · auto-updates ~15 min.</div>', unsafe_allow_html=True)
