"""RMSE_BOT dashboard — redesigned, per-coin pages with LIVE charts (Streamlit).

Sidebar navigation: Overview + a dedicated page per account (gold/BTC/ETH/SOL/ADA/DOGE).
Each coin page shows account stats, equity curve, open/closed trades, and a LIVE
candlestick price chart from Binance PUBLIC data (no API key needed — identical data).
All times shown in PKT (Pakistan, UTC+5). Account state read from the GitHub repo (raw).
Deploy: share.streamlit.io -> repo husnaina87926-creator/rmse-bot, branch main, dashboard/app.py
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd
import altair as alt
import streamlit as st

RAW = "https://raw.githubusercontent.com/husnaina87926-creator/rmse-bot/main"
BINANCE = "https://data-api.binance.vision/api/v3"      # PUBLIC market data (no key)
START = 5000.0
PKT = timezone(timedelta(hours=5))                       # Pakistan Standard Time (UTC+5, no DST)
CYAN, PURPLE, GREEN, RED, GOLD = "#00e5ff", "#a855f7", "#00ffa3", "#ff4d6d", "#ffd24a"

# account key -> (label, accent colour, Binance chart symbol). Gold charts via PAXG (tokenised gold).
ACCOUNTS = [
    ("gold", "🥇 Gold", GOLD, "PAXGUSDT"),
    ("btc", "₿ BTC", "#f7931a", "BTCUSDT"),
    ("eth", "⟠ ETH", "#8a92b2", "ETHUSDT"),
    ("sol", "◎ SOL", "#14f195", "SOLUSDT"),
    ("ada", "🔷 ADA", "#4d7bf3", "ADAUSDT"),
    ("dog", "🐕 DOGE", "#c2a633", "DOGEUSDT"),
]
ACC = {k: (lbl, col, sym) for k, lbl, col, sym in ACCOUNTS}

st.set_page_config(page_title="RMSE_BOT", page_icon="🤖", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Rajdhani:wght@500;600;700&display=swap');
#MainMenu, header, footer {visibility:hidden;}
.stApp { background:
   radial-gradient(1200px 600px at 12% -10%, rgba(0,229,255,0.10), transparent 60%),
   radial-gradient(1000px 520px at 92% 0%, rgba(168,85,247,0.13), transparent 55%), #060912 fixed;
   color:#e6edf7; font-family:'Rajdhani',sans-serif; }
.block-container { padding-top:1rem; max-width:1240px; }
section[data-testid="stSidebar"] { background:rgba(10,15,28,0.92); border-right:1px solid rgba(0,229,255,0.12); }
h1,h2,h3 { font-family:'Orbitron',sans-serif !important; letter-spacing:1px; }
.hero { font-family:'Orbitron'; font-size:1.9rem; font-weight:800;
   background:linear-gradient(90deg,#00e5ff,#a855f7); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.sub { color:#7d8db0; font-size:0.9rem; margin-bottom:12px; }
.sect { font-family:'Orbitron'; font-size:1rem; margin:22px 0 10px; color:#cfe9ff;
   border-left:3px solid #00e5ff; padding-left:10px; }
.kpi-grid { display:flex; flex-wrap:wrap; gap:14px; }
.kpi { flex:1 1 150px; background:rgba(255,255,255,0.035); backdrop-filter:blur(10px);
   border:1px solid rgba(0,229,255,0.18); border-radius:16px; padding:16px 18px; box-shadow:0 0 22px rgba(0,229,255,0.07); }
.kpi-t { font-size:0.76rem; color:#8aa0c6; text-transform:uppercase; letter-spacing:1px; }
.kpi-v { font-family:'Orbitron'; font-size:1.55rem; font-weight:800; margin-top:4px; text-shadow:0 0 18px currentColor; }
.kpi-s { font-size:0.82rem; color:#7d8db0; margin-top:2px; }
.acard { background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:14px; padding:14px 16px; }
.acard .nm { font-family:'Orbitron'; font-size:1rem; }
.acard .bal { font-family:'Orbitron'; font-size:1.5rem; font-weight:800; margin-top:6px; }
.tbl-wrap { overflow-x:auto; border-radius:14px; border:1px solid rgba(255,255,255,0.07); background:rgba(255,255,255,0.025); }
table.ft { width:100%; border-collapse:collapse; font-size:0.9rem; min-width:440px; }
table.ft th { text-align:left; padding:9px 12px; color:#9fb3d6; font-weight:700; text-transform:uppercase; font-size:0.7rem; border-bottom:1px solid rgba(255,255,255,0.08); }
table.ft td { padding:8px 12px; border-bottom:1px solid rgba(255,255,255,0.05); }
.pos { color:#00ffa3; font-weight:700; } .neg { color:#ff4d6d; font-weight:700; }
.pill { padding:2px 9px; border-radius:999px; font-size:0.72rem; font-weight:700; }
.pill.buy,.pill.tp,.pill.win { background:rgba(0,255,163,0.13); color:#00ffa3; }
.pill.sell { background:rgba(255,210,74,0.14); color:#ffd24a; }
.pill.sl,.pill.loss { background:rgba(255,77,109,0.13); color:#ff4d6d; }
.pill.time { background:rgba(0,229,255,0.12); color:#00e5ff; }
.big-price { font-family:'Orbitron'; font-size:2.1rem; font-weight:800; }
.chg { font-family:'Orbitron'; font-size:1rem; padding:3px 10px; border-radius:10px; }
.foot { color:#5d6b88; font-size:0.78rem; margin-top:22px; }
@media (max-width:640px){ .hero{font-size:1.4rem;} .kpi-v{font-size:1.25rem;} .block-container{padding:0.6rem;} .big-price{font-size:1.6rem;} }
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


@st.cache_data(ttl=90)
def fetch_klines(symbol, interval="1h", limit=168):
    """Live OHLC from Binance PUBLIC data. Times converted to PKT (UTC+5)."""
    try:
        url = f"{BINANCE}/klines?symbol={symbol}&interval={interval}&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "rmse-dash"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        df = pd.DataFrame(data, columns=["t", "o", "h", "l", "c", "v", "T", "q", "n", "B", "Q", "X"])
        df["time"] = pd.to_datetime(df["t"], unit="ms") + pd.Timedelta(hours=5)   # -> PKT
        for col in ("o", "h", "l", "c"):
            df[col] = df[col].astype(float)
        return df
    except Exception:
        return None


@st.cache_data(ttl=90)
def fetch_ticker(symbol):
    try:
        url = f"{BINANCE}/ticker/24hr?symbol={symbol}"
        req = urllib.request.Request(url, headers={"User-Agent": "rmse-dash"})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read().decode())
        return float(d["lastPrice"]), float(d["priceChangePercent"])
    except Exception:
        return None, None


def stats(s):
    closed = (s or {}).get("closed", [])
    wins = [t for t in closed if t["pnl"] > 0]
    return {"balance": (s or {}).get("balance", START), "trades": len(closed),
            "open": len((s or {}).get("open", [])),
            "win": (len(wins) / len(closed) if closed else 0.0),
            "pnl": sum(t["pnl"] for t in closed)}


def money(x):
    return f'<span class="{"pos" if x >= 0 else "neg"}">${x:+,.2f}</span>'


def pkt(iso):
    """ISO/UTC string -> 'YYYY-MM-DD HH:MM PKT'."""
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(PKT).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso)[:16]


def table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table class="ft"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def candles(df, color):
    base = alt.Chart(df).encode(
        x=alt.X("time:T", title=None, axis=alt.Axis(labelColor="#7d8db0", grid=False, domain=False)))
    rule = base.mark_rule().encode(
        y=alt.Y("l:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(labelColor="#7d8db0", gridColor="rgba(255,255,255,0.06)", domain=False)),
        y2="h:Q",
        color=alt.condition("datum.o <= datum.c", alt.value(GREEN), alt.value(RED)))
    body = base.mark_bar(size=5).encode(
        y="o:Q", y2="c:Q",
        color=alt.condition("datum.o <= datum.c", alt.value(GREEN), alt.value(RED)))
    return (rule + body).properties(height=300).configure_view(strokeWidth=0).configure(background="rgba(0,0,0,0)")


def equity(closed, color):
    eq = pd.DataFrame({"#": range(len(closed) + 1),
                       "Balance": [START] + [t["balance_after"] for t in closed]})
    return alt.Chart(eq).mark_area(
        line={"color": color, "strokeWidth": 2.5},
        color=alt.Gradient(gradient="linear",
            stops=[alt.GradientStop(color=color, offset=0), alt.GradientStop(color="rgba(0,0,0,0)", offset=1)],
            x1=1, x2=1, y1=1, y2=0)
    ).encode(
        x=alt.X("#:Q", title=None, axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False)),
        y=alt.Y("Balance:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(grid=True, gridColor="rgba(255,255,255,0.06)", domain=False)),
    ).properties(height=200).configure_view(strokeWidth=0).configure(background="rgba(0,0,0,0)")


# ---------------- load all state ----------------
states = {k: load_json(f"state/{k}.json") for k, _, _, _ in ACCOUNTS}
now_pkt = datetime.now(PKT).strftime("%Y-%m-%d %H:%M")

# ---------------- sidebar nav ----------------
st.sidebar.markdown('<div class="hero">⚡ RMSE&nbsp;BOT</div>', unsafe_allow_html=True)
st.sidebar.caption(f"🕒 {now_pkt} PKT")
page = st.sidebar.radio("Navigate", ["📊 Overview"] + [lbl for _, lbl, _, _ in ACCOUNTS], label_visibility="collapsed")
if st.sidebar.button("🔄 Refresh data"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.markdown('<div class="foot">Paper trading · virtual $5000/account<br>Times in PKT · data: Binance public + GitHub</div>',
                    unsafe_allow_html=True)

if not any(states.values()):
    st.warning("State load nahi hua — thori dair baad Refresh karein.")
    st.stop()

# ================= OVERVIEW =================
if page.startswith("📊"):
    st.markdown('<div class="hero">📊 Portfolio Overview</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub">{len(ACCOUNTS)} autonomous paper accounts · all-weather · forward-test · {now_pkt} PKT</div>',
                unsafe_allow_html=True)
    tb = sum(stats(states[k])["balance"] for k, _, _, _ in ACCOUNTS)
    tp = sum(stats(states[k])["pnl"] for k, _, _, _ in ACCOUNTS)
    tt = sum(stats(states[k])["trades"] for k, _, _, _ in ACCOUNTS)
    to = sum(stats(states[k])["open"] for k, _, _, _ in ACCOUNTS)
    st_tot = START * len(ACCOUNTS)
    kpis = [("Total Balance", f"${tb:,.0f}", f"{tb-st_tot:+,.0f} from ${st_tot:,.0f}", GREEN if tb >= st_tot else RED),
            ("Total P&L", f"${tp:+,.0f}", f"realized ({len(ACCOUNTS)} accounts)", GREEN if tp >= 0 else RED),
            ("Total Trades", f"{tt}", f"{to} open now", CYAN),
            ("Accounts", f"{len(ACCOUNTS)}", "gold · BTC · ETH · SOL · ADA · DOGE", PURPLE)]
    st.markdown('<div class="kpi-grid">' + "".join(
        f'<div class="kpi"><div class="kpi-t">{t}</div><div class="kpi-v" style="color:{c}">{v}</div>'
        f'<div class="kpi-s">{sb}</div></div>' for t, v, sb, c in kpis) + '</div>', unsafe_allow_html=True)

    st.markdown('<div class="sect">📂 Accounts — click a coin in the sidebar for its live page</div>', unsafe_allow_html=True)
    rows = [ACCOUNTS[i:i + 3] for i in range(0, len(ACCOUNTS), 3)]
    for grp in rows:
        cols = st.columns(len(grp))
        for col, (k, lbl, color, _) in zip(cols, grp):
            a = stats(states[k])
            bcol = GREEN if a["balance"] >= START else RED
            col.markdown(
                f'<div class="acard"><div class="nm" style="color:{color}">{lbl}</div>'
                f'<div class="bal" style="color:{bcol}">${a["balance"]:,.0f}</div>'
                f'<div class="kpi-s">P&L {money(a["pnl"])} · {a["trades"]} tr · win {a["win"]*100:.0f}% · {a["open"]} open</div></div>',
                unsafe_allow_html=True)

# ================= PER-COIN PAGE =================
else:
    k = next(kk for kk, lbl, _, _ in ACCOUNTS if lbl == page)
    lbl, color, sym = ACC[k]
    s = states[k] or {}
    a = stats(s)

    # header + live price
    last, chg = fetch_ticker(sym)
    st.markdown(f'<div class="hero" style="color:{color};-webkit-text-fill-color:{color};background:none">{lbl}</div>',
                unsafe_allow_html=True)
    note = "gold ~ PAXG (tokenised gold) proxy" if k == "gold" else f"{sym} · Binance live"
    st.markdown(f'<div class="sub">{note} · all times PKT · {now_pkt}</div>', unsafe_allow_html=True)
    if last is not None:
        cc = GREEN if (chg or 0) >= 0 else RED
        st.markdown(
            f'<span class="big-price" style="color:{color}">${last:,.4f}</span> &nbsp; '
            f'<span class="chg" style="background:rgba(255,255,255,0.05);color:{cc}">{chg:+.2f}% (24h)</span>',
            unsafe_allow_html=True)

    # account KPIs
    bcol = GREEN if a["balance"] >= START else RED
    kpis = [("Balance", f"${a['balance']:,.0f}", f"{a['balance']-START:+,.0f} P&L", bcol),
            ("Win rate", f"{a['win']*100:.0f}%", f"{a['trades']} closed trades", CYAN),
            ("Open now", f"{a['open']}", "live positions", PURPLE),
            ("Realized P&L", f"${a['pnl']:+,.0f}", "since $5000 start", GREEN if a['pnl'] >= 0 else RED)]
    st.markdown('<div class="kpi-grid">' + "".join(
        f'<div class="kpi"><div class="kpi-t">{t}</div><div class="kpi-v" style="color:{c}">{v}</div>'
        f'<div class="kpi-s">{sb}</div></div>' for t, v, sb, c in kpis) + '</div>', unsafe_allow_html=True)

    # equity curve
    closed = s.get("closed", [])
    if closed:
        st.markdown('<div class="sect">📈 Account equity</div>', unsafe_allow_html=True)
        st.altair_chart(equity(closed, color), use_container_width=True)

    # open + closed trades
    op = s.get("open", [])
    if op:
        st.markdown('<div class="sect">🔓 Open positions</div>', unsafe_allow_html=True)
        st.markdown(table(["Symbol", "Dir", "Entry", "SL", "TP", "Opened (PKT)"],
            [[p["symbol"], f'<span class="pill {p["direction"]}">{p["direction"].upper()}</span>',
              f'{p["entry"]:,.4f}', f'{p.get("sl",0):,.4f}', f'{p.get("tp",0):,.4f}', pkt(p["open_time"])] for p in op]),
            unsafe_allow_html=True)
    if closed:
        st.markdown('<div class="sect">📜 Recent closed trades</div>', unsafe_allow_html=True)
        st.markdown(table(["Symbol", "Dir", "Result", "P&L", "Closed (PKT)"],
            [[t["symbol"], f'<span class="pill {t["direction"]}">{t["direction"].upper()}</span>',
              f'<span class="pill {t["outcome"]}">{t["outcome"].upper()}</span>', money(t["pnl"]), pkt(t["close_time"])]
             for t in reversed(closed[-15:])]), unsafe_allow_html=True)
    if not closed and not op:
        st.markdown('<div class="sub">Abhi koi trade nahi — bot sahi mauqe ka intezar mein (regime/signal).</div>',
                    unsafe_allow_html=True)

    # LIVE price chart (the main request: graph at the bottom of each coin page)
    st.markdown('<div class="sect">🕯️ Live price chart</div>', unsafe_allow_html=True)
    rng = st.radio("Range", ["24H", "7D", "30D"], horizontal=True, label_visibility="collapsed")
    interval, limit = {"24H": ("15m", 96), "7D": ("1h", 168), "30D": ("4h", 180)}[rng]
    kl = fetch_klines(sym, interval, limit)
    if kl is not None and len(kl):
        st.altair_chart(candles(kl, color), use_container_width=True)
        st.caption(f"{sym} · {rng} · {interval} candles · Binance public data · PKT")
    else:
        st.info("Live chart abhi load nahi hua — Refresh karein.")

st.markdown('<div class="foot">⚠️ Paper trading (virtual $5000/account). Past ≠ future. Not financial advice. '
            'Prices: Binance public API (no key) · account state: GitHub (~15 min). Times: PKT (UTC+5).</div>',
            unsafe_allow_html=True)
