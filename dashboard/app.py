"""RMSE_BOT dashboard — professional CLAYMORPHISM redesign (Streamlit, dark).

Design system (via ui-ux-pro-max): dark claymorphism — soft extruded clay surfaces with
dual inner+outer shadows, chunky radii, fintech palette (gold + slate + violet accent),
Plus Jakarta Sans (display) + Inter (data, tabular numbers). Sidebar nav -> Overview +
a page per account, each with KPIs, equity curve, trade tables, and a LIVE candlestick
chart from Binance PUBLIC data (no API key). All times PKT (UTC+5). Reduced-motion safe.
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
PKT = timezone(timedelta(hours=5))                       # Pakistan Standard Time (UTC+5)

# palette
GOLD, VIOLET, GREEN, RED, CYAN = "#f5b544", "#8b5cf6", "#34d39a", "#ff5d73", "#37c2e0"
# account key -> (label, accent, glyph, Binance chart symbol). Gold charts via PAXG.
ACCOUNTS = [
    ("gold", "Gold", GOLD, "Au", "PAXGUSDT"),
    ("btc", "Bitcoin", "#f7931a", "₿", "BTCUSDT"),
    ("eth", "Ethereum", "#9aa6c4", "Ξ", "ETHUSDT"),
    ("sol", "Solana", "#14f195", "◎", "SOLUSDT"),
    ("ada", "Cardano", "#4d8df7", "₳", "ADAUSDT"),
    ("dog", "Dogecoin", "#cba64a", "Ð", "DOGEUSDT"),
]
ACC = {k: (lbl, col, gl, sym) for k, lbl, col, gl, sym in ACCOUNTS}


def darken(hexc, f=0.62):
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
    return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"


st.set_page_config(page_title="RMSE_BOT", page_icon="◈", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap');
:root{
  --bg:#10131c; --surf-hi:#222a40; --surf-lo:#161b29; --text:#eef2fb; --muted:#8b97b4;
  --gold:#f5b544; --violet:#8b5cf6; --green:#34d39a; --red:#ff5d73; --cyan:#37c2e0;
  --r-card:26px; --r-kpi:22px; --r-pill:13px;
  --clay:11px 11px 24px rgba(0,0,0,.52), -8px -8px 20px rgba(255,255,255,.022),
         inset 1px 1px 2px rgba(255,255,255,.07), inset -2px -3px 9px rgba(0,0,0,.34);
  --clay-sm:6px 6px 15px rgba(0,0,0,.46), -4px -4px 11px rgba(255,255,255,.02),
            inset 1px 1px 1px rgba(255,255,255,.06);
}
#MainMenu, header, footer {visibility:hidden;}
.stApp{ background:
   radial-gradient(1100px 560px at 10% -8%, rgba(245,181,68,.06), transparent 60%),
   radial-gradient(1000px 520px at 95% 0%, rgba(139,92,246,.08), transparent 58%), var(--bg) fixed;
   color:var(--text); font-family:'Inter',sans-serif; }
.block-container{ padding-top:1.1rem; max-width:1240px; }
h1,h2,h3{ font-family:'Plus Jakarta Sans',sans-serif !important; letter-spacing:-.3px; }
.num{ font-variant-numeric:tabular-nums; }
.hero{ font-family:'Plus Jakarta Sans'; font-size:1.75rem; font-weight:800; letter-spacing:-.5px;
   background:linear-gradient(95deg,var(--gold),#ffd98a 40%,var(--violet)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.sub{ color:var(--muted); font-size:.9rem; margin:2px 0 16px; font-weight:500; }
.sect{ font-family:'Plus Jakarta Sans'; font-size:.96rem; font-weight:700; margin:26px 0 12px; color:#d9e4fb;
   display:flex; align-items:center; gap:9px; }
.sect:before{ content:""; width:9px; height:18px; border-radius:5px; background:linear-gradient(var(--gold),var(--violet)); box-shadow:var(--clay-sm); }

/* clay surface */
.clay{ background:linear-gradient(150deg,var(--surf-hi),var(--surf-lo)); border-radius:var(--r-card); box-shadow:var(--clay); }
.kpi-grid{ display:flex; flex-wrap:wrap; gap:16px; }
.kpi{ flex:1 1 165px; background:linear-gradient(150deg,var(--surf-hi),var(--surf-lo));
   border-radius:var(--r-kpi); box-shadow:var(--clay); padding:17px 19px; transition:transform .22s cubic-bezier(.34,1.4,.4,1), box-shadow .22s ease; }
.kpi:hover{ transform:translateY(-3px); }
.kpi-t{ font-size:.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:1.3px; font-weight:600; }
.kpi-v{ font-family:'Plus Jakarta Sans'; font-size:1.62rem; font-weight:800; margin-top:5px; }
.kpi-s{ font-size:.82rem; color:var(--muted); margin-top:3px; font-weight:500; }

.acard{ background:linear-gradient(150deg,var(--surf-hi),var(--surf-lo)); border-radius:var(--r-card);
   box-shadow:var(--clay); padding:18px; transition:transform .22s cubic-bezier(.34,1.4,.4,1); }
.acard:hover{ transform:translateY(-4px); }
.ac-top{ display:flex; align-items:center; gap:12px; margin-bottom:13px; }
.badge{ width:48px; height:48px; border-radius:16px; display:flex; align-items:center; justify-content:center;
   font-family:'Plus Jakarta Sans'; font-weight:800; font-size:1.25rem; color:#10131c; flex:0 0 auto;
   box-shadow:5px 5px 12px rgba(0,0,0,.45), -3px -3px 9px rgba(255,255,255,.05),
              inset 2px 2px 5px rgba(255,255,255,.45), inset -3px -3px 7px rgba(0,0,0,.30); }
.ac-nm{ font-family:'Plus Jakarta Sans'; font-weight:700; font-size:1.02rem; }
.ac-sym{ font-size:.74rem; color:var(--muted); font-weight:500; letter-spacing:.5px; }
.ac-bal{ font-family:'Plus Jakarta Sans'; font-size:1.7rem; font-weight:800; }
.ac-stats{ font-size:.82rem; color:var(--muted); margin-top:4px; font-weight:500; }

.price-panel{ background:linear-gradient(150deg,var(--surf-hi),var(--surf-lo)); border-radius:var(--r-card);
   box-shadow:var(--clay); padding:18px 22px; display:flex; align-items:center; gap:18px; flex-wrap:wrap; margin-bottom:18px; }
.big-price{ font-family:'Plus Jakarta Sans'; font-size:2.2rem; font-weight:800; }
.chg{ font-family:'Plus Jakarta Sans'; font-size:1rem; font-weight:700; padding:6px 13px; border-radius:13px; box-shadow:var(--clay-sm); }

.pos{ color:var(--green); font-weight:700; } .neg{ color:var(--red); font-weight:700; }
.tbl-wrap{ overflow-x:auto; border-radius:20px; box-shadow:var(--clay); background:linear-gradient(150deg,var(--surf-hi),var(--surf-lo)); padding:4px; }
table.ft{ width:100%; border-collapse:collapse; font-size:.9rem; min-width:460px; }
table.ft th{ text-align:left; padding:11px 14px; color:#9fb0d4; font-weight:600; text-transform:uppercase; font-size:.68rem; letter-spacing:.8px; }
table.ft td{ padding:10px 14px; border-top:1px solid rgba(255,255,255,.045); font-variant-numeric:tabular-nums; }
.pill{ padding:3px 11px; border-radius:999px; font-size:.72rem; font-weight:700; }
.pill.buy,.pill.tp,.pill.win{ background:rgba(52,211,154,.16); color:var(--green); }
.pill.sell{ background:rgba(245,181,68,.17); color:var(--gold); }
.pill.sl,.pill.loss{ background:rgba(255,93,115,.16); color:var(--red); }
.pill.time{ background:rgba(55,194,224,.15); color:var(--cyan); }

/* sidebar */
section[data-testid="stSidebar"]{ background:linear-gradient(180deg,#141925,#0e121b); border-right:1px solid rgba(255,255,255,.04); }
section[data-testid="stSidebar"] .stRadio > div{ gap:8px; }
section[data-testid="stSidebar"] .stRadio label{ background:linear-gradient(150deg,#212940,#161b29);
   box-shadow:var(--clay-sm); border-radius:14px; padding:10px 14px !important; margin:0; transition:transform .18s ease; font-weight:600; }
section[data-testid="stSidebar"] .stRadio label:hover{ transform:translateX(3px); }
.stButton>button{ background:linear-gradient(150deg,#212940,#161b29); color:var(--gold); border:none;
   border-radius:14px; font-family:'Plus Jakarta Sans'; font-weight:700; font-size:.82rem; box-shadow:var(--clay-sm);
   padding:9px 16px; transition:transform .18s ease; width:100%; }
.stButton>button:hover{ transform:translateY(-2px); color:#ffd98a; }
.stButton>button:active{ transform:scale(.96); }
div[role="radiogroup"][aria-label] label{ font-size:.86rem; }
.foot{ color:#67738f; font-size:.78rem; margin-top:24px; line-height:1.5; }
@media (prefers-reduced-motion: reduce){ *{ transition:none !important; animation:none !important; } }
@media (max-width:640px){ .hero{font-size:1.35rem;} .kpi-v{font-size:1.3rem;} .big-price{font-size:1.6rem;} .block-container{padding:.6rem;} }
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
    try:
        url = f"{BINANCE}/klines?symbol={symbol}&interval={interval}&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "rmse-dash"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        df = pd.DataFrame(data, columns=["t", "o", "h", "l", "c", "v", "T", "q", "n", "B", "Q", "X"])
        df["time"] = pd.to_datetime(df["t"], unit="ms") + pd.Timedelta(hours=5)
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
    return f'<span class="num {"pos" if x >= 0 else "neg"}">${x:+,.2f}</span>'


def pkt(iso):
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(PKT).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso)[:16]


def kpi_html(items):
    return '<div class="kpi-grid">' + "".join(
        f'<div class="kpi"><div class="kpi-t">{t}</div><div class="kpi-v num" style="color:{c}">{v}</div>'
        f'<div class="kpi-s">{sb}</div></div>' for t, v, sb, c in items) + '</div>'


def table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table class="ft"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def candles(df, color):
    base = alt.Chart(df).encode(
        x=alt.X("time:T", title=None, axis=alt.Axis(labelColor="#8b97b4", grid=False, domain=False, tickColor="#2a3247")))
    rule = base.mark_rule(strokeWidth=1).encode(
        y=alt.Y("l:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(labelColor="#8b97b4", gridColor="rgba(255,255,255,.045)", domain=False, tickColor="#2a3247")),
        y2="h:Q", color=alt.condition("datum.o <= datum.c", alt.value(GREEN), alt.value(RED)))
    body = base.mark_bar(size=6, cornerRadius=2).encode(
        y="o:Q", y2="c:Q", color=alt.condition("datum.o <= datum.c", alt.value(GREEN), alt.value(RED)))
    return (rule + body).properties(height=320).configure_view(strokeWidth=0).configure(background="rgba(0,0,0,0)")


def equity(closed, color):
    eq = pd.DataFrame({"#": range(len(closed) + 1), "Balance": [START] + [t["balance_after"] for t in closed]})
    return alt.Chart(eq).mark_area(
        line={"color": color, "strokeWidth": 3},
        color=alt.Gradient(gradient="linear",
            stops=[alt.GradientStop(color=color, offset=0), alt.GradientStop(color="rgba(0,0,0,0)", offset=1)],
            x1=1, x2=1, y1=1, y2=0)
    ).encode(
        x=alt.X("#:Q", title=None, axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False)),
        y=alt.Y("Balance:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(grid=True, gridColor="rgba(255,255,255,.045)", domain=False, labelColor="#8b97b4")),
    ).properties(height=210).configure_view(strokeWidth=0).configure(background="rgba(0,0,0,0)")


def badge(color, glyph):
    return f'<div class="badge" style="background:linear-gradient(150deg,{color},{darken(color)})">{glyph}</div>'


# ---------------- load ----------------
states = {k: load_json(f"state/{k}.json") for k, *_ in ACCOUNTS}
now_pkt = datetime.now(PKT).strftime("%Y-%m-%d %H:%M")

# ---------------- sidebar ----------------
st.sidebar.markdown('<div class="hero">◈ RMSE&nbsp;BOT</div>', unsafe_allow_html=True)
st.sidebar.markdown(f'<div class="sub">🕒 {now_pkt} PKT</div>', unsafe_allow_html=True)
page = st.sidebar.radio("nav", ["Overview"] + [lbl for _, lbl, *_ in ACCOUNTS], label_visibility="collapsed")
if st.sidebar.button("⟳  Refresh data"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.markdown('<div class="foot">Paper trading · virtual $5000 / account.<br>Times PKT (UTC+5). '
                    'Prices: Binance public · state: GitHub.</div>', unsafe_allow_html=True)

if not any(states.values()):
    st.warning("State load nahi hua — thori dair baad Refresh karein.")
    st.stop()

# ================= OVERVIEW =================
if page == "Overview":
    st.markdown('<div class="hero">Portfolio Overview</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sub">{len(ACCOUNTS)} autonomous paper accounts · all-weather strategy · live forward-test · {now_pkt} PKT</div>',
                unsafe_allow_html=True)
    tb = sum(stats(states[k])["balance"] for k, *_ in ACCOUNTS)
    tp = sum(stats(states[k])["pnl"] for k, *_ in ACCOUNTS)
    tt = sum(stats(states[k])["trades"] for k, *_ in ACCOUNTS)
    to = sum(stats(states[k])["open"] for k, *_ in ACCOUNTS)
    st_tot = START * len(ACCOUNTS)
    st.markdown(kpi_html([
        ("Total Balance", f"${tb:,.0f}", f"{tb-st_tot:+,.0f} from ${st_tot:,.0f}", GREEN if tb >= st_tot else RED),
        ("Realized P&L", f"${tp:+,.0f}", f"across {len(ACCOUNTS)} accounts", GREEN if tp >= 0 else RED),
        ("Total Trades", f"{tt}", f"{to} open right now", CYAN),
        ("Accounts", f"{len(ACCOUNTS)}", "diversified all-weather", VIOLET)]), unsafe_allow_html=True)

    st.markdown('<div class="sect">Accounts — open a coin from the sidebar for its live page</div>', unsafe_allow_html=True)
    for i in range(0, len(ACCOUNTS), 3):
        grp = ACCOUNTS[i:i + 3]
        cols = st.columns(len(grp))
        for col, (k, lbl, color, gl, sym) in zip(cols, grp):
            a = stats(states[k])
            bcol = GREEN if a["balance"] >= START else RED
            col.markdown(
                f'<div class="acard"><div class="ac-top">{badge(color, gl)}'
                f'<div><div class="ac-nm">{lbl}</div><div class="ac-sym">{sym}</div></div></div>'
                f'<div class="ac-bal num" style="color:{bcol}">${a["balance"]:,.0f}</div>'
                f'<div class="ac-stats">P&L {money(a["pnl"])} · {a["trades"]} tr · win {a["win"]*100:.0f}% · {a["open"]} open</div></div>',
                unsafe_allow_html=True)

# ================= PER-COIN =================
else:
    k = next(kk for kk, lbl, *_ in ACCOUNTS if lbl == page)
    lbl, color, gl, sym = ACC[k]
    s = states[k] or {}
    a = stats(s)
    last, chg = fetch_ticker(sym)

    st.markdown(f'<div style="display:flex;align-items:center;gap:14px;margin-bottom:2px">{badge(color, gl)}'
                f'<div class="hero" style="background:none;-webkit-text-fill-color:{color};color:{color}">{lbl}</div></div>',
                unsafe_allow_html=True)
    note = "gold ≈ PAXG (tokenised gold) proxy" if k == "gold" else f"{sym} · Binance live"
    st.markdown(f'<div class="sub">{note} · times in PKT · {now_pkt}</div>', unsafe_allow_html=True)
    if last is not None:
        cc = GREEN if (chg or 0) >= 0 else RED
        arrow = "▲" if (chg or 0) >= 0 else "▼"
        st.markdown(
            f'<div class="price-panel"><span class="big-price num" style="color:{color}">${last:,.4f}</span>'
            f'<span class="chg num" style="color:{cc}">{arrow} {abs(chg):.2f}% <span style="color:var(--muted);font-weight:500">24h</span></span></div>',
            unsafe_allow_html=True)

    bcol = GREEN if a["balance"] >= START else RED
    st.markdown(kpi_html([
        ("Balance", f"${a['balance']:,.0f}", f"{a['balance']-START:+,.0f} P&L", bcol),
        ("Win rate", f"{a['win']*100:.0f}%", f"{a['trades']} closed trades", CYAN),
        ("Open now", f"{a['open']}", "live positions", VIOLET),
        ("Realized P&L", f"${a['pnl']:+,.0f}", "since $5,000 start", GREEN if a['pnl'] >= 0 else RED)]),
        unsafe_allow_html=True)

    closed = s.get("closed", [])
    if closed:
        st.markdown('<div class="sect">Account equity</div>', unsafe_allow_html=True)
        st.altair_chart(equity(closed, color), use_container_width=True)

    op = s.get("open", [])
    if op:
        st.markdown('<div class="sect">Open positions</div>', unsafe_allow_html=True)
        st.markdown(table(["Symbol", "Dir", "Entry", "Stop", "Target", "Opened (PKT)"],
            [[p["symbol"], f'<span class="pill {p["direction"]}">{p["direction"].upper()}</span>',
              f'{p["entry"]:,.4f}', f'{p.get("sl",0):,.4f}', f'{p.get("tp",0):,.4f}', pkt(p["open_time"])] for p in op]),
            unsafe_allow_html=True)
    if closed:
        st.markdown('<div class="sect">Recent closed trades</div>', unsafe_allow_html=True)
        st.markdown(table(["Symbol", "Dir", "Result", "P&L", "Closed (PKT)"],
            [[t["symbol"], f'<span class="pill {t["direction"]}">{t["direction"].upper()}</span>',
              f'<span class="pill {t["outcome"]}">{t["outcome"].upper()}</span>', money(t["pnl"]), pkt(t["close_time"])]
             for t in reversed(closed[-15:])]), unsafe_allow_html=True)
    if not closed and not op:
        st.markdown('<div class="sub">Abhi koi trade nahi — bot sahi mauqe ka intezar mein (regime / signal).</div>',
                    unsafe_allow_html=True)

    st.markdown('<div class="sect">Live price chart</div>', unsafe_allow_html=True)
    rng = st.radio("range", ["24H", "7D", "30D"], horizontal=True, label_visibility="collapsed")
    interval, limit = {"24H": ("15m", 96), "7D": ("1h", 168), "30D": ("4h", 180)}[rng]
    kl = fetch_klines(sym, interval, limit)
    if kl is not None and len(kl):
        st.altair_chart(candles(kl, color), use_container_width=True)
        st.caption(f"{sym} · {rng} · {interval} candles · Binance public data · PKT")
    else:
        st.info("Live chart abhi load nahi hua — Refresh karein.")

st.markdown('<div class="foot">⚠️ Paper trading (virtual $5,000 / account). Past ≠ future. Not financial advice. '
            'Prices: Binance public API (no key). Account state: GitHub (~15 min). Times: PKT (UTC+5).</div>',
            unsafe_allow_html=True)
