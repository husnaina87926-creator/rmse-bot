"""RMSE_BOT dashboard — BENTO GRID design (Streamlit, light, device-responsive).

Modular Apple/Vercel-style bento tiles of varied sizes, soft shadows, rounded-24,
indigo accent. Top pill nav (no sidebar) works on phone/tablet/desktop. Per-coin pages
with live Binance candlestick charts (public data, no key), equity curves, trade tables.
All times PKT (UTC+5). State read from the GitHub repo (raw).
Deploy: share.streamlit.io -> repo husnaina87926-creator/rmse-bot, branch main, dashboard/app.py
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd
import altair as alt
import streamlit as st

RAW = "https://raw.githubusercontent.com/husnaina87926-creator/rmse-bot/main"
BINANCE = "https://data-api.binance.vision/api/v3"
START = 5000.0
PKT = timezone(timedelta(hours=5))
BRAND, GREEN, RED, INK, MUT = "#635bff", "#12b76a", "#e5484d", "#16181d", "#8b909c"

ACCOUNTS = [
    ("gold", "Gold", "#f5b544", "Au", "PAXGUSDT"),
    ("btc", "Bitcoin", "#f7931a", "₿", "BTCUSDT"),
    ("eth", "Ethereum", "#7b86a8", "Ξ", "ETHUSDT"),
    ("sol", "Solana", "#12b981", "◎", "SOLUSDT"),
    ("ada", "Cardano", "#4d8df7", "₳", "ADAUSDT"),
    ("doge", "Dogecoin", "#c2a12e", "Ð", "DOGEUSDT"),
    ("op", "Optimism", "#ff5168", "OP", "OPUSDT"),
    ("sei", "Sei", "#c4504a", "SE", "SEIUSDT"),
    ("vet", "VeChain", "#15a5e0", "VE", "VETUSDT"),
    ("gala", "Gala", "#ff7a5c", "GA", "GALAUSDT"),
    ("xtz", "Tezos", "#4d8df7", "ꜩ", "XTZUSDT"),
    ("sand", "The Sandbox", "#22a5d4", "SA", "SANDUSDT"),
    ("mana", "Decentraland", "#e5484d", "MA", "MANAUSDT"),
    ("hbar", "Hedera", "#5b6472", "ℏ", "HBARUSDT"),
]
ACC = {k: (lbl, col, gl, sym) for k, lbl, col, gl, sym in ACCOUNTS}

st.set_page_config(page_title="RMSE_BOT", page_icon="◈", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
*{box-sizing:border-box}
:root{ --bg:#f4f4f7; --card:#ffffff; --ink:#16181d; --mut:#8b909c; --line:#ececf1; --soft:#f7f7fa;
  --brand:#635bff; --green:#12b76a; --red:#e5484d; --r:22px;
  --sh:0 2px 10px rgba(20,22,30,.06); --sh-h:0 10px 28px rgba(20,22,30,.12); }
#MainMenu, header, footer {visibility:hidden;}
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"], [data-testid="stSidebarCollapseButton"]{ display:none !important; }
.stApp, [data-testid="stAppViewContainer"]{ background:var(--bg); color:var(--ink);
  font-family:'Inter',sans-serif; }
.block-container{ padding-top:1.1rem; max-width:1200px; }
h1,h2,h3{ font-family:'Inter',sans-serif !important; }
.num{ font-variant-numeric:tabular-nums; }
.pos{ color:var(--green); font-weight:700; } .neg{ color:var(--red); font-weight:700; }

.brand{ font-size:1.35rem; font-weight:800; letter-spacing:-.5px; color:var(--ink); }
.brand b{ color:var(--brand); }
.sub{ color:var(--mut); font-size:.86rem; font-weight:500; margin-top:1px; }
.sect{ font-size:.72rem; letter-spacing:1.3px; text-transform:uppercase; color:var(--mut);
  font-weight:700; margin:26px 0 12px; }

/* pill nav */
.navwrap{ background:#fff; border-radius:16px; padding:8px; box-shadow:var(--sh); margin:10px 0 22px; }
div[role="radiogroup"]{ display:flex; gap:6px; flex-wrap:wrap; }
div[role="radiogroup"] label{ background:var(--soft); border-radius:11px; padding:8px 14px; min-height:40px;
  display:flex; align-items:center; font-weight:600; font-size:.84rem; color:#4a5163; cursor:pointer;
  border:1px solid transparent; transition:all .15s; }
div[role="radiogroup"] label:hover{ background:#eef0ff; color:var(--brand); }
div[role="radiogroup"] label:has(input:checked){ background:var(--brand); color:#fff; box-shadow:0 4px 12px rgba(99,91,255,.35); }
div[role="radiogroup"] label > div:first-child{ display:none; }

/* bento grid */
.bento{ display:grid; grid-template-columns:repeat(4,1fr); grid-auto-rows:150px; gap:16px; }
.t{ border-radius:var(--r); background:var(--card); box-shadow:var(--sh); padding:20px;
  transition:transform .2s, box-shadow .2s; display:flex; flex-direction:column; overflow:hidden; }
.t:hover{ transform:translateY(-3px); box-shadow:var(--sh-h); }
.lab{ font-size:.7rem; color:var(--mut); text-transform:uppercase; letter-spacing:1px; font-weight:700; }
.val{ font-size:1.9rem; font-weight:800; letter-spacing:-1px; margin-top:6px; color:var(--ink); }
.small{ font-size:.78rem; color:var(--mut); margin-top:3px; font-weight:500; }
.span2{ grid-column:span 2; } .row2{ grid-row:span 2; }
.hero{ grid-column:span 2; grid-row:span 2; background:linear-gradient(150deg,#6c63ff,#8b7bff); color:#fff; }
.hero .lab{ color:rgba(255,255,255,.85); } .hero .big{ font-size:3rem; font-weight:800; letter-spacing:-2px; margin-top:8px; }
.hero .hs{ margin-top:auto; font-size:.86rem; color:rgba(255,255,255,.92); font-weight:500; }
.full{ grid-column:span 4; }

/* account chips inside a bento card */
.clist{ display:grid; grid-template-columns:repeat(auto-fill,minmax(148px,1fr)); gap:12px; margin-top:14px; }
.cc{ background:var(--soft); border:1px solid var(--line); border-radius:16px; padding:13px; transition:transform .15s; }
.cc:hover{ transform:translateY(-2px); border-color:#dcdcf5; }
.cc .r{ display:flex; align-items:center; gap:8px; }
.cc .ic{ width:30px; height:30px; border-radius:9px; display:grid; place-items:center; font-weight:800; font-size:.78rem; color:#fff; }
.cc .nm{ font-weight:700; font-size:.86rem; color:var(--ink); }
.cc .bal{ font-size:1.15rem; font-weight:800; margin-top:9px; letter-spacing:-.5px; }
.cc .m{ font-size:.72rem; color:var(--mut); margin-top:2px; font-weight:500; }

/* coin header + price */
.chead{ display:flex; align-items:center; gap:14px; }
.cic{ width:52px; height:52px; border-radius:15px; display:grid; place-items:center; font-weight:800; font-size:1.35rem; color:#fff; box-shadow:var(--sh); }
.cname{ font-size:1.5rem; font-weight:800; letter-spacing:-.5px; }
.csym{ font-size:.8rem; color:var(--mut); font-weight:500; }
.price{ font-size:2.1rem; font-weight:800; letter-spacing:-1px; }
.chg{ font-size:.95rem; font-weight:700; padding:5px 12px; border-radius:11px; }

/* tables */
.tcard{ background:#fff; border-radius:var(--r); box-shadow:var(--sh); padding:6px; overflow-x:auto; }
table.ft{ width:100%; border-collapse:collapse; font-size:.88rem; min-width:420px; }
table.ft th{ text-align:left; padding:11px 14px; color:var(--mut); font-weight:600; text-transform:uppercase;
  font-size:.66rem; letter-spacing:.7px; border-bottom:1px solid var(--line); }
table.ft td{ padding:11px 14px; border-bottom:1px solid #f3f3f7; font-variant-numeric:tabular-nums; }
table.ft tr:last-child td{ border-bottom:none; }
.pill{ padding:3px 10px; border-radius:999px; font-size:.72rem; font-weight:700; }
.pill.buy,.pill.tp{ background:rgba(18,183,106,.12); color:var(--green); }
.pill.sell{ background:rgba(245,181,68,.16); color:#b7791f; }
.pill.sl{ background:rgba(229,72,77,.12); color:var(--red); }
.pill.time{ background:rgba(99,91,255,.12); color:var(--brand); }
.dot{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:8px; vertical-align:middle; }

.stButton>button{ background:var(--ink); color:#fff; border:none; border-radius:999px;
  font-weight:600; font-size:.82rem; padding:9px 16px; min-height:42px; transition:transform .15s; }
.stButton>button:hover{ transform:translateY(-2px); background:#000; }
.foot{ color:#a4a9b8; font-size:.76rem; margin-top:26px; line-height:1.5; }

@media(max-width:820px){ .bento{ grid-template-columns:repeat(2,1fr); } .hero,.span2,.full{ grid-column:span 2; }
  .price{font-size:1.7rem;} .cname{font-size:1.25rem;} }
@media(max-width:480px){ .bento{ gap:12px; grid-auto-rows:132px; } .hero .big{font-size:2.3rem;} .val{font-size:1.55rem;}
  .block-container{padding:.6rem;} table.ft{min-width:360px;} }
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
    return f'<span class="num {"pos" if x >= 0 else "neg"}">{"+" if x>=0 else "−"}${abs(x):,.0f}</span>'


def pkt(iso):
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
    return f'<div class="tcard"><table class="ft"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def candles(df, up=GREEN, dn=RED):
    base = alt.Chart(df).encode(
        x=alt.X("time:T", title=None, axis=alt.Axis(labelColor=MUT, grid=False, domainColor="#e6e6ee", tickColor="#e6e6ee")))
    rule = base.mark_rule(strokeWidth=1).encode(
        y=alt.Y("l:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(labelColor=MUT, gridColor="#eef0f4", domain=False, tickColor="#e6e6ee")),
        y2="h:Q", color=alt.condition("datum.o <= datum.c", alt.value(up), alt.value(dn)))
    body = base.mark_bar(size=6, cornerRadius=2).encode(
        y="o:Q", y2="c:Q", color=alt.condition("datum.o <= datum.c", alt.value(up), alt.value(dn)))
    return (rule + body).properties(height=320).configure_view(strokeWidth=0).configure(background="#ffffff")


def equity(closed, color=BRAND):
    eq = pd.DataFrame({"#": range(len(closed) + 1), "Balance": [START] + [t["balance_after"] for t in closed]})
    return alt.Chart(eq).mark_area(
        line={"color": color, "strokeWidth": 3},
        color=alt.Gradient(gradient="linear",
            stops=[alt.GradientStop(color=color, offset=0), alt.GradientStop(color="#ffffff", offset=1)],
            x1=1, x2=1, y1=1, y2=0)
    ).encode(
        x=alt.X("#:Q", title=None, axis=alt.Axis(labels=False, ticks=False, domain=False, grid=False)),
        y=alt.Y("Balance:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(grid=True, gridColor="#eef0f4", domain=False, labelColor=MUT)),
    ).properties(height=210).configure_view(strokeWidth=0).configure(background="#ffffff")


# ---------------- load ----------------
states = {k: load_json(f"state/{k}.json") for k, *_ in ACCOUNTS}
now_pkt = datetime.now(PKT).strftime("%Y-%m-%d %H:%M")

# ---------------- top bar + nav ----------------
c1, c2 = st.columns([4, 1])
c1.markdown(f'<div class="brand">◈ RMSE <b>BOT</b></div>'
            f'<div class="sub">🕒 {now_pkt} PKT · {len(ACCOUNTS)} paper accounts · live forward-test</div>',
            unsafe_allow_html=True)
with c2:
    if st.button("⟳ Refresh", key="refresh_btn", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

NAV_DISP = {"Overview": "◧ Overview"}
for _k, _lbl, _c, _gl, _sym in ACCOUNTS:
    NAV_DISP[_lbl] = f"{_gl} {_k.upper()}"
_opts = ["Overview"] + [lbl for _, lbl, *_ in ACCOUNTS]
st.markdown('<div class="navwrap">', unsafe_allow_html=True)
page = st.radio("nav", _opts, format_func=lambda o: NAV_DISP[o], horizontal=True, label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

if not any(states.values()):
    st.warning("State load nahi hua — thori dair baad Refresh karein.")
    st.stop()

# ================= OVERVIEW (BENTO) =================
if page == "Overview":
    tb = sum(stats(states[k])["balance"] for k, *_ in ACCOUNTS)
    tp = sum(stats(states[k])["pnl"] for k, *_ in ACCOUNTS)
    tt = sum(stats(states[k])["trades"] for k, *_ in ACCOUNTS)
    to = sum(stats(states[k])["open"] for k, *_ in ACCOUNTS)
    st_tot = START * len(ACCOUNTS)
    # best account
    best_k, best = max(((k, stats(states[k])) for k, *_ in ACCOUNTS), key=lambda x: x[1]["pnl"])
    best_lbl = ACC[best_k][0]
    pnl_pct = (tp / st_tot) * 100

    chips = ""
    for k, lbl, color, gl, sym in ACCOUNTS:
        a = stats(states[k]); bcol = GREEN if a["balance"] >= START else (RED if a["balance"] < START else INK)
        chips += (f'<div class="cc"><div class="r"><div class="ic" style="background:{color}">{gl}</div>'
                  f'<div class="nm">{k.upper()}</div></div>'
                  f'<div class="bal" style="color:{bcol if a["pnl"] else INK}">${a["balance"]:,.0f}</div>'
                  f'<div class="m">{money(a["pnl"])} · win {a["win"]*100:.0f}% · {a["trades"]}tr</div></div>')

    st.markdown(f"""
    <div class="bento">
      <div class="t hero">
        <div class="lab">Total equity</div>
        <div class="big num">${tb:,.0f}</div>
        <div class="hs">▲ +${tb-st_tot:,.0f} ({pnl_pct:+.1f}%) · {len(ACCOUNTS)} accounts · live forward-test</div>
      </div>
      <div class="t"><div class="lab">Realized P&amp;L</div>
        <div class="val" style="color:{GREEN if tp>=0 else RED}">{'+' if tp>=0 else '−'}${abs(tp):,.0f}</div>
        <div class="small">across {len(ACCOUNTS)} accounts</div></div>
      <div class="t"><div class="lab">Total trades</div>
        <div class="val num">{tt}</div><div class="small">{to} open now</div></div>
      <div class="t span2"><div class="lab">Best account · {best_lbl}</div>
        <div class="val" style="color:{GREEN if best['pnl']>=0 else RED}">{'+' if best['pnl']>=0 else '−'}${abs(best['pnl']):,.0f}</div>
        <div class="small">balance ${best['balance']:,.0f} · win {best['win']*100:.0f}%</div></div>
      <div class="t full" style="grid-row:span 2;">
        <div class="lab">All accounts — tap a coin in the top bar for its live page</div>
        <div class="clist">{chips}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ================= PER-COIN (BENTO) =================
else:
    k = next(kk for kk, lbl, *_ in ACCOUNTS if lbl == page)
    lbl, color, gl, sym = ACC[k]
    s = states[k] or {}
    a = stats(s)
    last, chg = fetch_ticker(sym)

    st.markdown(f'<div class="chead"><div class="cic" style="background:{color}">{gl}</div>'
                f'<div><div class="cname">{lbl}</div>'
                f'<div class="csym">{("gold ≈ PAXG proxy" if k=="gold" else sym+" · Binance live")} · {now_pkt} PKT</div></div></div>',
                unsafe_allow_html=True)

    # bento tiles: price + KPIs
    bcol = GREEN if a["balance"] >= START else (RED if a["balance"] < START else INK)
    price_tile = ""
    if last is not None:
        cc = GREEN if (chg or 0) >= 0 else RED
        arrow = "▲" if (chg or 0) >= 0 else "▼"
        price_tile = (f'<div class="t span2"><div class="lab">Live price · {sym}</div>'
                      f'<div style="display:flex;align-items:baseline;gap:12px;margin-top:8px">'
                      f'<span class="price" style="color:{color}">${last:,.4f}</span>'
                      f'<span class="chg" style="background:rgba(99,91,255,.08);color:{cc}">{arrow} {abs(chg):.2f}% 24h</span></div></div>')
    st.markdown(f"""
    <div class="bento" style="grid-auto-rows:auto;">
      {price_tile}
      <div class="t"><div class="lab">Balance</div><div class="val" style="color:{bcol}">${a['balance']:,.0f}</div>
        <div class="small">{money(a['pnl'])} P&amp;L</div></div>
      <div class="t"><div class="lab">Win rate</div><div class="val num">{a['win']*100:.0f}%</div>
        <div class="small">{a['trades']} closed · {a['open']} open</div></div>
    </div>
    """, unsafe_allow_html=True)

    closed = s.get("closed", [])
    if closed:
        st.markdown('<div class="sect">Account equity</div>', unsafe_allow_html=True)
        st.altair_chart(equity(closed), use_container_width=True)

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
        st.markdown('<div class="sub" style="margin-top:14px">Abhi koi trade nahi — bot sahi mauqe ka intezar mein (regime / signal).</div>',
                    unsafe_allow_html=True)

    st.markdown('<div class="sect">Live price chart</div>', unsafe_allow_html=True)
    rng = st.radio("range", ["24H", "7D", "30D"], horizontal=True, label_visibility="collapsed")
    interval, limit = {"24H": ("15m", 96), "7D": ("1h", 168), "30D": ("4h", 180)}[rng]
    kl = fetch_klines(sym, interval, limit)
    if kl is not None and len(kl):
        st.altair_chart(candles(kl), use_container_width=True)
        st.caption(f"{sym} · {rng} · {interval} candles · Binance public data · PKT")
    else:
        st.info("Live chart abhi load nahi hua — Refresh karein.")

st.markdown('<div class="foot">⚠️ Paper trading (virtual $5,000 / account). Past ≠ future. Not financial advice. '
            'Prices: Binance public API (no key). Account state: GitHub (~15 min). Times: PKT (UTC+5).</div>',
            unsafe_allow_html=True)
