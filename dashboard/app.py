"""RMSE_BOT dashboard — OBSIDIAN TERMINAL design (Streamlit, premium dark, device-responsive).

Deep-space dark trading terminal: bento stat tiles, per-account SVG sparklines, animated
gradient hero, CSS scroll-reveal (animation-timeline: view(), graceful fallback), pulsing
live dot, status colors (green/red/amber), tabular numerals everywhere. Pages: Overview,
Brain (self-learning activity: graduation gate, tournament, scoreboard, shadow exits,
regime watch, sentiment, mistake diary), one page per coin (live price, candles, equity,
trades). All times PKT (UTC+5). State from GitHub raw (cloud) or local files (VPS copy).
Deploy: share.streamlit.io -> repo husnaina87926-creator/rmse-bot, branch main, dashboard/app.py
"""
import json
import inspect
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd
import altair as alt
import streamlit as st

# full-width kwarg that works on both old and new Streamlit versions
_WIDE = ({"width": "stretch"} if "width" in inspect.signature(st.button).parameters
         else {"use_container_width": True})

RAW = "https://raw.githubusercontent.com/husnaina87926-creator/rmse-bot/main"
BINANCE = "https://data-api.binance.vision/api/v3"
START = 5000.0
PKT = timezone(timedelta(hours=5))

INK, MUT, LINE = "#e7ecf5", "#8b93a7", "rgba(148,163,184,.10)"
GREEN, RED, AMBER, BRAND, CYAN = "#34d399", "#fb7185", "#fbbf24", "#818cf8", "#22d3ee"
BG, CARD = "#0a0d14", "#10151f"

ACCOUNTS = [
    ("gold", "Gold", "#f5b544", "Au", "PAXGUSDT"),
    ("btc", "Bitcoin", "#f7931a", "₿", "BTCUSDT"),
    ("eth", "Ethereum", "#9aa7d8", "Ξ", "ETHUSDT"),
    ("sol", "Solana", "#2fd6a7", "◎", "SOLUSDT"),
    ("ada", "Cardano", "#5b9dff", "₳", "ADAUSDT"),
    ("doge", "Dogecoin", "#d8b94a", "Ð", "DOGEUSDT"),
    ("op", "Optimism", "#ff5f74", "OP", "OPUSDT"),
    ("sei", "Sei", "#e06a63", "SE", "SEIUSDT"),
    ("vet", "VeChain", "#38b6ff", "VE", "VETUSDT"),
    ("gala", "Gala", "#ff8a68", "GA", "GALAUSDT"),
    ("xtz", "Tezos", "#6ea8ff", "ꜩ", "XTZUSDT"),
    ("sand", "The Sandbox", "#3fb9e6", "SA", "SANDUSDT"),
    ("mana", "Decentraland", "#ff7d92", "MA", "MANAUSDT"),
    ("hbar", "Hedera", "#8f9bb3", "ℏ", "HBARUSDT"),
]
ACC = {k: (lbl, col, gl, sym) for k, lbl, col, gl, sym in ACCOUNTS}

st.set_page_config(page_title="RMSE_BOT", page_icon="◈", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
*{{box-sizing:border-box}}
:root{{ --bg:{BG}; --card:{CARD}; --card2:#141b29; --ink:{INK}; --mut:{MUT};
  --line:{LINE}; --brand:{BRAND}; --cyan:{CYAN}; --green:{GREEN}; --red:{RED}; --amber:{AMBER};
  --r:20px; --sh:0 1px 0 rgba(255,255,255,.03) inset, 0 12px 34px rgba(0,0,0,.45); }}
#MainMenu, header, footer {{visibility:hidden;}}
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"], [data-testid="stSidebarCollapseButton"]{{ display:none !important; }}
.stApp, [data-testid="stAppViewContainer"]{{
  background:
    radial-gradient(1100px 500px at 85% -10%, rgba(99,102,241,.16), transparent 60%),
    radial-gradient(900px 420px at -10% 8%, rgba(34,211,238,.10), transparent 55%),
    var(--bg);
  color:var(--ink); font-family:'Inter',sans-serif; }}
.block-container{{ padding-top:1rem; max-width:1240px; }}
h1,h2,h3{{ font-family:'Space Grotesk',sans-serif !important; }}
.num, table.ft td{{ font-family:'JetBrains Mono',monospace; font-variant-numeric:tabular-nums; }}
.pos{{ color:var(--green); font-weight:700; }} .neg{{ color:var(--red); font-weight:700; }}

/* ---------- brand bar ---------- */
.brand{{ font-family:'Space Grotesk',sans-serif; font-size:1.42rem; font-weight:700;
  letter-spacing:-.4px; color:var(--ink); display:flex; align-items:center; gap:10px; }}
.brand b{{ background:linear-gradient(90deg,var(--brand),var(--cyan));
  -webkit-background-clip:text; background-clip:text; color:transparent; }}
.livedot{{ width:9px; height:9px; border-radius:50%; background:var(--green);
  box-shadow:0 0 0 0 rgba(52,211,153,.55); animation:pulse 2.2s infinite; }}
@keyframes pulse{{ 70%{{ box-shadow:0 0 0 9px rgba(52,211,153,0); }} }}
.sub{{ color:var(--mut); font-size:.84rem; font-weight:500; margin-top:2px; }}
.sect{{ font-family:'Space Grotesk',sans-serif; font-size:.74rem; letter-spacing:2px;
  text-transform:uppercase; color:var(--mut); font-weight:600; margin:30px 0 12px;
  display:flex; align-items:center; gap:10px; }}
.sect:after{{ content:""; flex:1; height:1px; background:linear-gradient(90deg,var(--line),transparent); }}

/* ---------- pill nav ---------- */
.navwrap{{ background:rgba(16,21,31,.75); backdrop-filter:blur(14px); border:1px solid var(--line);
  border-radius:16px; padding:8px; box-shadow:var(--sh); margin:12px 0 20px; }}
div[role="radiogroup"]{{ display:flex; gap:6px; flex-wrap:wrap; }}
div[role="radiogroup"] label{{ background:rgba(255,255,255,.03); border-radius:11px; padding:8px 14px;
  min-height:42px; display:flex; align-items:center; font-weight:600; font-size:.84rem;
  color:#aab2c5; cursor:pointer; border:1px solid transparent; transition:all .18s ease-out; }}
div[role="radiogroup"] label:hover{{ background:rgba(129,140,248,.12); color:var(--ink);
  transform:translateY(-1px); }}
div[role="radiogroup"] label:has(input:checked){{
  background:linear-gradient(135deg,rgba(99,102,241,.9),rgba(34,211,238,.75)); color:#fff;
  box-shadow:0 6px 18px rgba(99,102,241,.35); }}
div[role="radiogroup"] label > div:first-child{{ display:none; }}
div[role="radiogroup"] label p{{ color:inherit !important; }}

/* ---------- bento grid + tiles ---------- */
.bento{{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }}
.t{{ border-radius:var(--r); background:linear-gradient(180deg,var(--card2),var(--card));
  border:1px solid var(--line); box-shadow:var(--sh); padding:20px;
  display:flex; flex-direction:column; overflow:hidden; position:relative;
  transition:transform .22s ease-out, border-color .22s; }}
.t:hover{{ transform:translateY(-3px); border-color:rgba(129,140,248,.35); }}
.lab{{ font-size:.68rem; color:var(--mut); text-transform:uppercase; letter-spacing:1.4px; font-weight:600; }}
.val{{ font-family:'JetBrains Mono',monospace; font-size:1.75rem; font-weight:700;
  letter-spacing:-1px; margin-top:8px; color:var(--ink); font-variant-numeric:tabular-nums; }}
.small{{ font-size:.78rem; color:var(--mut); margin-top:4px; font-weight:500; }}
.span2{{ grid-column:span 2; }} .full{{ grid-column:span 4; }}
.hero{{ grid-column:span 2; grid-row:span 2; color:#fff; border:1px solid rgba(129,140,248,.35);
  background:linear-gradient(120deg,#161c34,#101527 45%,#0d1f2a);
  background-size:200% 200%; animation:heroflow 9s ease infinite; }}
@keyframes heroflow{{ 0%,100%{{background-position:0% 50%}} 50%{{background-position:100% 50%}} }}
.hero .big{{ font-family:'JetBrains Mono',monospace; font-size:2.9rem; font-weight:700;
  letter-spacing:-2px; margin-top:10px; background:linear-gradient(90deg,#fff,#c7d2fe);
  -webkit-background-clip:text; background-clip:text; color:transparent; }}
.hero .hs{{ margin-top:auto; font-size:.85rem; color:#b8c1d9; font-weight:500; }}

/* ---------- account cards with sparklines ---------- */
.clist{{ display:grid; grid-template-columns:repeat(auto-fill,minmax(168px,1fr)); gap:12px; margin-top:14px; }}
.cc{{ background:rgba(255,255,255,.025); border:1px solid var(--line); border-radius:16px;
  padding:14px 14px 10px; transition:transform .18s ease-out, border-color .18s; position:relative; }}
.cc:hover{{ transform:translateY(-3px); border-color:rgba(129,140,248,.4); }}
.cc .r{{ display:flex; align-items:center; gap:8px; }}
.cc .ic{{ width:28px; height:28px; border-radius:9px; display:grid; place-items:center;
  font-weight:800; font-size:.74rem; color:#0a0d14; }}
.cc .nm{{ font-weight:700; font-size:.85rem; color:var(--ink); letter-spacing:.3px; }}
.cc .bal{{ font-family:'JetBrains Mono',monospace; font-size:1.12rem; font-weight:700;
  margin-top:9px; letter-spacing:-.5px; }}
.cc .m{{ font-size:.7rem; color:var(--mut); margin-top:2px; font-weight:500; }}
.cc svg{{ display:block; margin-top:8px; width:100%; height:34px; }}

/* ---------- coin header ---------- */
.chead{{ display:flex; align-items:center; gap:14px; }}
.cic{{ width:52px; height:52px; border-radius:15px; display:grid; place-items:center; font-weight:800;
  font-size:1.3rem; color:#0a0d14; box-shadow:0 8px 24px rgba(0,0,0,.4); }}
.cname{{ font-family:'Space Grotesk',sans-serif; font-size:1.5rem; font-weight:700; letter-spacing:-.4px; }}
.csym{{ font-size:.78rem; color:var(--mut); font-weight:500; }}
.price{{ font-family:'JetBrains Mono',monospace; font-size:2rem; font-weight:700; letter-spacing:-1px; }}
.chg{{ font-family:'JetBrains Mono',monospace; font-size:.9rem; font-weight:700; padding:5px 12px;
  border-radius:11px; background:rgba(255,255,255,.05); }}

/* ---------- tables ---------- */
.tcard{{ background:linear-gradient(180deg,var(--card2),var(--card)); border:1px solid var(--line);
  border-radius:var(--r); box-shadow:var(--sh); padding:6px; overflow-x:auto; }}
table.ft{{ width:100%; border-collapse:collapse; font-size:.85rem; min-width:430px; }}
table.ft th{{ text-align:left; padding:11px 14px; color:var(--mut); font-weight:600;
  text-transform:uppercase; font-size:.64rem; letter-spacing:1px; border-bottom:1px solid var(--line); }}
table.ft td{{ padding:11px 14px; border-bottom:1px solid rgba(148,163,184,.05); color:var(--ink); }}
table.ft tr:last-child td{{ border-bottom:none; }}
table.ft tbody tr{{ transition:background .15s; }}
table.ft tbody tr:hover{{ background:rgba(129,140,248,.06); }}
.pill{{ padding:3px 10px; border-radius:999px; font-size:.7rem; font-weight:700; letter-spacing:.4px; }}
.pill.buy,.pill.tp{{ background:rgba(52,211,153,.14); color:var(--green); }}
.pill.sell{{ background:rgba(251,191,36,.14); color:var(--amber); }}
.pill.sl{{ background:rgba(251,113,133,.14); color:var(--red); }}
.pill.time,.pill.win,.pill.loss{{ background:rgba(129,140,248,.14); color:var(--brand); }}

/* ---------- gate progress ---------- */
.gbar{{ height:10px; border-radius:999px; background:rgba(255,255,255,.06); overflow:hidden; margin-top:12px; }}
.gfill{{ height:100%; border-radius:999px; background:linear-gradient(90deg,var(--brand),var(--cyan));
  box-shadow:0 0 14px rgba(34,211,238,.5); transition:width 1s ease-out; }}

/* ---------- buttons ---------- */
.stButton>button{{ background:linear-gradient(135deg,var(--brand),#5b64f0); color:#fff; border:none;
  border-radius:999px; font-weight:600; font-size:.82rem; padding:9px 16px; min-height:42px;
  transition:transform .16s ease-out, box-shadow .16s; }}
.stButton>button:hover{{ transform:translateY(-2px); box-shadow:0 8px 22px rgba(99,102,241,.4); }}
.foot{{ color:#5d6577; font-size:.75rem; margin-top:30px; line-height:1.6; }}

/* ---------- entrance + scroll-reveal animations (CSS only) ---------- */
@keyframes rise{{ from{{ opacity:0; transform:translateY(18px); }} to{{ opacity:1; transform:none; }} }}
.bento .t{{ animation:rise .5s ease-out both; }}
.bento .t:nth-child(1){{animation-delay:.03s}} .bento .t:nth-child(2){{animation-delay:.09s}}
.bento .t:nth-child(3){{animation-delay:.15s}} .bento .t:nth-child(4){{animation-delay:.21s}}
.bento .t:nth-child(5){{animation-delay:.27s}} .bento .t:nth-child(6){{animation-delay:.33s}}
.cc{{ animation:rise .45s ease-out both; }}
.clist .cc:nth-child(odd){{ animation-delay:.05s }} .clist .cc:nth-child(3n){{ animation-delay:.12s }}
@supports (animation-timeline: view()) {{
  .tcard, .sect, .reveal{{ animation:rise .6s ease-out both;
    animation-timeline:view(); animation-range:entry 0% entry 45%; }}
}}
@media (prefers-reduced-motion: reduce) {{
  *, *:before, *:after{{ animation-duration:.001s !important; animation-delay:0s !important;
    transition-duration:.001s !important; }}
}}

/* ---------- responsive ---------- */
@media(max-width:820px){{
  .bento{{ grid-template-columns:repeat(2,1fr); }} .hero,.span2,.full{{ grid-column:span 2; }}
  .price{{font-size:1.6rem;}} .cname{{font-size:1.2rem;}} .hero .big{{font-size:2.3rem;}}
  .navwrap div[role="radiogroup"]{{ flex-wrap:nowrap; overflow-x:auto;
    -webkit-overflow-scrolling:touch; scrollbar-width:none; padding-bottom:2px; }}
  .navwrap div[role="radiogroup"]::-webkit-scrollbar{{ display:none; }}
  .navwrap div[role="radiogroup"] label{{ flex:0 0 auto; white-space:nowrap; }} }}
@media(max-width:480px){{
  .bento{{ gap:11px; }} .val{{font-size:1.4rem;}} .hero .big{{font-size:2rem;}}
  .block-container{{padding:.6rem;}} table.ft{{min-width:380px;}} }}
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


def money(x, dec=0):
    return (f'<span class="num {"pos" if x >= 0 else "neg"}">'
            f'{"+" if x >= 0 else "−"}${abs(x):,.{dec}f}</span>')


def pkt(iso):
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(PKT).strftime("%d %b %H:%M")
    except Exception:
        return str(iso)[:16]


def table(headers, rows):
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return (f'<div class="tcard"><table class="ft"><thead><tr>{th}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def spark(closed, color=GREEN, w=150, h=34, n=40):
    """Inline SVG equity sparkline from an account's closed trades."""
    vals = [START] + [t.get("balance_after", START) for t in closed]
    vals = vals[-n:]
    if len(vals) < 2:
        vals = [START, START]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    pts = [(i * w / (len(vals) - 1), h - 3 - (v - lo) / rng * (h - 6))
           for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{h} " + line + f" {w},{h}"
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polygon points="{area}" fill="{color}" opacity="0.10"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


_AXIS = dict(labelColor=MUT, gridColor="rgba(148,163,184,.08)", domain=False,
             tickColor="rgba(148,163,184,.15)")


def candles(df):
    base = alt.Chart(df).encode(
        x=alt.X("time:T", title=None,
                axis=alt.Axis(labelColor=MUT, grid=False, domainColor="rgba(148,163,184,.15)",
                              tickColor="rgba(148,163,184,.15)")))
    rule = base.mark_rule(strokeWidth=1).encode(
        y=alt.Y("l:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(**_AXIS)),
        y2="h:Q", color=alt.condition("datum.o <= datum.c", alt.value(GREEN), alt.value(RED)))
    body = base.mark_bar(size=6, cornerRadius=2).encode(
        y="o:Q", y2="c:Q",
        color=alt.condition("datum.o <= datum.c", alt.value(GREEN), alt.value(RED)))
    return ((rule + body).properties(height=320)
            .configure_view(strokeWidth=0).configure(background="transparent"))


def equity(closed, color=BRAND):
    eq = pd.DataFrame({"#": range(len(closed) + 1),
                       "Balance": [START] + [t["balance_after"] for t in closed]})
    return (alt.Chart(eq).mark_area(
        line={"color": color, "strokeWidth": 2.5},
        color=alt.Gradient(gradient="linear",
            stops=[alt.GradientStop(color=color, offset=0),
                   alt.GradientStop(color="transparent", offset=1)],
            x1=1, x2=1, y1=1, y2=0))
        .encode(
            x=alt.X("#:Q", title=None, axis=alt.Axis(labels=False, ticks=False,
                                                     domain=False, grid=False)),
            y=alt.Y("Balance:Q", title=None, scale=alt.Scale(zero=False),
                    axis=alt.Axis(grid=True, **_AXIS)))
        .properties(height=210).configure_view(strokeWidth=0)
        .configure(background="transparent"))


# ---------------- load all state ----------------
states = {k: load_json(f"state/{k}.json") for k, *_ in ACCOUNTS}
watch = load_json("state/regime_watch.json") or {}
gate = load_json("state/graduation.json")
senti = load_json("state/news_sentiment.json")
hb = load_json("state/brain_heartbeat.json")
cands = load_json("state/candidates.json") or {}
now_pkt = datetime.now(PKT).strftime("%d %b %Y · %H:%M")

# ---------------- top bar + nav ----------------
c1, c2 = st.columns([4, 1])
c1.markdown(f'<div class="brand"><span class="livedot"></span> RMSE <b>BOT</b></div>'
            f'<div class="sub">{now_pkt} PKT · {len(ACCOUNTS)} paper accounts · '
            f'always-on forward test</div>', unsafe_allow_html=True)
with c2:
    if st.button("⟳ Refresh", key="refresh_btn", **_WIDE):
        st.cache_data.clear()
        st.rerun()

NAV_DISP = {"Overview": "◧ Overview", "Brain": "◉ BRAIN"}
for _k, _lbl, _c, _gl, _sym in ACCOUNTS:
    NAV_DISP[_lbl] = f"{_gl} {_k.upper()}"
_opts = ["Overview", "Brain"] + [lbl for _, lbl, *_ in ACCOUNTS]
st.markdown('<div class="navwrap">', unsafe_allow_html=True)
page = st.radio("nav", _opts, format_func=lambda o: NAV_DISP[o],
                horizontal=True, label_visibility="collapsed")
st.markdown('</div>', unsafe_allow_html=True)

if not any(states.values()):
    st.warning("State load nahi hua — thori dair baad Refresh karein.")
    st.stop()

# ================= OVERVIEW =================
if page == "Overview":
    A = {k: stats(states[k]) for k, *_ in ACCOUNTS}
    tb = sum(a["balance"] for a in A.values())
    tp = sum(a["pnl"] for a in A.values())
    tt = sum(a["trades"] for a in A.values())
    to = sum(a["open"] for a in A.values())
    st_tot = START * len(ACCOUNTS)
    all_closed = [t for k, *_ in ACCOUNTS for t in (states[k] or {}).get("closed", [])]
    wins_all = [t for t in all_closed if t["pnl"] > 0]
    win_all = len(wins_all) / len(all_closed) if all_closed else 0.0
    gross_w = sum(t["pnl"] for t in wins_all)
    gross_l = -sum(t["pnl"] for t in all_closed if t["pnl"] < 0)
    pf_all = (gross_w / gross_l) if gross_l else 0.0
    best_k, best = max(A.items(), key=lambda x: x[1]["pnl"])
    worst_k, worst = min(A.items(), key=lambda x: x[1]["pnl"])
    pnl_pct = (tp / st_tot) * 100
    arrow = "▲ +" if tb >= st_tot else "▼ −"

    up_n = sum(1 for w in watch.values() if isinstance(w, dict) and w.get("regime") == "up")
    dn_n = sum(1 for w in watch.values() if isinstance(w, dict) and w.get("regime") == "down")
    gp, gt = (gate.get("passed", 0), gate.get("total", 7)) if gate else (0, 7)
    s_mkt = senti.get("market") if senti else None
    n_cands = sum(len(v) if isinstance(v, list) else 1 for v in cands.values())

    st.markdown(f"""
    <div class="bento">
      <div class="t hero">
        <div class="lab">Total equity — {len(ACCOUNTS)} accounts</div>
        <div class="big">${tb:,.0f}</div>
        <div class="hs">{arrow}${abs(tb - st_tot):,.0f} ({pnl_pct:+.2f}%) since start ·
          win {win_all * 100:.0f}% · PF {pf_all:.2f} · {to} open now</div>
      </div>
      <div class="t"><div class="lab">Realized P&amp;L</div>
        <div class="val" style="color:{GREEN if tp >= 0 else RED}">{'+' if tp >= 0 else '−'}${abs(tp):,.0f}</div>
        <div class="small">{tt} closed trades</div></div>
      <div class="t"><div class="lab">Market regime</div>
        <div class="val"><span style="color:{GREEN}">{up_n}▲</span> <span style="color:{RED}">{dn_n}▼</span></div>
        <div class="small">daily trend, {len(watch) or len(ACCOUNTS)} markets</div></div>
      <div class="t"><div class="lab">Best · {ACC[best_k][0]}</div>
        <div class="val" style="color:{GREEN if best['pnl'] >= 0 else RED}">{'+' if best['pnl'] >= 0 else '−'}${abs(best['pnl']):,.0f}</div>
        <div class="small">win {best['win'] * 100:.0f}% · {best['trades']} trades</div></div>
      <div class="t"><div class="lab">Weakest · {ACC[worst_k][0]}</div>
        <div class="val" style="color:{GREEN if worst['pnl'] >= 0 else RED}">{'+' if worst['pnl'] >= 0 else '−'}${abs(worst['pnl']):,.0f}</div>
        <div class="small">win {worst['win'] * 100:.0f}% · {worst['trades']} trades</div></div>
      <div class="t"><div class="lab">Graduation gate</div>
        <div class="val">{gp}<span style="color:{MUT}">/{gt}</span></div>
        <div class="gbar"><div class="gfill" style="width:{100 * gp / max(1, gt):.0f}%"></div></div></div>
      <div class="t"><div class="lab">News sentiment (LLM)</div>
        <div class="val" style="color:{GREEN if (s_mkt or 0) > 0 else (RED if (s_mkt or 0) < 0 else INK)}">{f"{s_mkt:+d}" if s_mkt is not None else "—"}</div>
        <div class="small">{(senti.get('top_risk') or '')[:52] if senti else 'observer off/idle'}</div></div>
      <div class="t span2"><div class="lab">Self-learning tournament</div>
        <div class="val">{n_cands} <span style="font-size:1rem;color:{MUT}">challengers in trial</span></div>
        <div class="small">discovery at every 4h close · promotion needs 30+ forward trades + t-stat</div></div>
    </div>""", unsafe_allow_html=True)

    st.markdown('<div class="sect">All 14 accounts — live equity</div>', unsafe_allow_html=True)
    chips = ""
    for k, lbl, color, gl, sym in ACCOUNTS:
        a = A[k]
        closed = (states[k] or {}).get("closed", [])
        pc = GREEN if a["pnl"] > 0 else (RED if a["pnl"] < 0 else INK)
        sc = GREEN if a["pnl"] >= 0 else RED
        reg = watch.get(sym.replace("PAXG", "XAU").replace("USDT", "USDT"), {})
        reg = (watch.get("XAUUSD") if k == "gold" else watch.get(sym)) or {}
        rr = reg.get("regime", "—") if isinstance(reg, dict) else "—"
        rc = GREEN if rr == "up" else (RED if rr == "down" else MUT)
        chips += (f'<div class="cc"><div class="r"><div class="ic" style="background:{color}">{gl}</div>'
                  f'<div class="nm">{k.upper()}</div>'
                  f'<div style="margin-left:auto;font-size:.62rem;font-weight:700;color:{rc};'
                  f'letter-spacing:1px">{rr.upper() if rr != "—" else ""}</div></div>'
                  f'<div class="bal" style="color:{pc}">${a["balance"]:,.0f}</div>'
                  f'<div class="m">{money(a["pnl"])} · win {a["win"] * 100:.0f}% · '
                  f'{a["trades"]}tr · {a["open"]} open</div>'
                  f'{spark(closed, sc)}</div>')
    st.markdown(f'<div class="clist">{chips}</div>', unsafe_allow_html=True)

    recent = sorted(all_closed, key=lambda t: str(t.get("close_time", "")), reverse=True)[:12]
    if recent:
        st.markdown('<div class="sect">Latest closed trades — whole portfolio</div>',
                    unsafe_allow_html=True)
        st.markdown(table(
            ["Market", "Dir", "Result", "P&L", "Closed (PKT)"],
            [[t.get("symbol", "?"),
              f'<span class="pill {t.get("direction", "buy")}">{t.get("direction", "?").upper()}</span>',
              f'<span class="pill {t.get("outcome", "time")}">{t.get("outcome", "?").upper()}</span>',
              money(t["pnl"], 2), pkt(t.get("close_time"))] for t in recent]),
            unsafe_allow_html=True)

# ================= BRAIN =================
elif page == "Brain":
    sb = load_json("state/scoreboard.json")
    lessons = load_json("state/lessons.json")
    health = load_json("state/health.json") or {}
    mistakes = load_json("state/mistakes.json")
    ledger = load_json("state/regime_ledger.json")

    alive, hb_txt = False, "no heartbeat on this copy"
    if hb and hb.get("ts"):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(hb["ts"])).total_seconds()
            alive = age < 3600
            hb_txt = f"last beat {int(age // 60)} min ago"
        except Exception:
            pass
    n_cands = sum(len(v) if isinstance(v, list) else 1 for v in cands.values())
    flags = [nm for nm, h in health.items() if isinstance(h, dict) and h.get("unhealthy")]
    gp, gt = (gate.get("passed", 0), gate.get("total", 7)) if gate else (0, 7)
    s_mkt = senti.get("market") if senti else None

    st.markdown(f"""
    <div class="bento">
      <div class="t hero"><div class="lab">Real-API graduation gate</div>
        <div class="big">{gp}/{gt}</div>
        <div class="gbar"><div class="gfill" style="width:{100 * gp / max(1, gt):.0f}%"></div></div>
        <div class="hs">{'🎓 GRADUATED — testnet step unlocked' if gate and gate.get('graduated')
                         else 'bot must EARN real-money access — no shortcuts'}</div></div>
      <div class="t"><div class="lab">Brain watchdog</div>
        <div class="val" style="color:{GREEN if alive else RED}">{'ALIVE' if alive else 'IDLE'}</div>
        <div class="small">{hb_txt}</div></div>
      <div class="t"><div class="lab">Tournament</div>
        <div class="val">{n_cands}</div>
        <div class="small">challengers in forward trial</div></div>
      <div class="t"><div class="lab">Health flags</div>
        <div class="val" style="color:{RED if flags else GREEN}">{len(flags) or 'NONE'}</div>
        <div class="small">{', '.join(flags[:4]) if flags else 'no account in decay'}</div></div>
      <div class="t"><div class="lab">News sentiment (LLM)</div>
        <div class="val" style="color:{GREEN if (s_mkt or 0) > 0 else (RED if (s_mkt or 0) < 0 else INK)}">{f"{s_mkt:+d} / ±2" if s_mkt is not None else 'OFF'}</div>
        <div class="small">{(senti.get('top_risk') or f"{senti.get('n_headlines', 0)} headlines read")[:60]
                            if senti else 'OPENAI_API_KEY set nahi'}</div></div>
    </div>""", unsafe_allow_html=True)

    if gate:
        st.markdown('<div class="sect">Graduation criteria — earn the real Binance API</div>',
                    unsafe_allow_html=True)
        st.markdown(table(["Criterion", "Now", "Target", "Status"],
            [[c["why"], f'{c["value"]}', c["target"],
              f'<span class="pill {"tp" if c["pass"] else "sl"}">{"PASS" if c["pass"] else "PENDING"}</span>']
             for c in gate.get("criteria", [])]), unsafe_allow_html=True)

    if cands:
        st.markdown('<div class="sect">Challenger tournament — forward trials</div>',
                    unsafe_allow_html=True)
        rows = []
        for sym_k, entry in sorted(cands.items()):
            for c in (entry if isinstance(entry, list) else [entry]):
                r = c.get("rule", {})
                rows.append([sym_k, f"slot {c.get('slot', 0)}",
                             f'<span class="pill {r.get("direction", "buy")}">{r.get("direction", "?").upper()}</span> '
                             + " & ".join(r.get("when", [])),
                             r.get("regime", "—"), c.get("pf", "—"),
                             str(c.get("born", ""))[:10]])
        st.markdown(table(["Symbol", "Slot", "Candidate rule", "Regime", "PF (backtest)", "Born"],
                          rows), unsafe_allow_html=True)

    if sb and sb.get("totals", {}).get("born"):
        t = sb["totals"]
        st.markdown('<div class="sect">Idea-family scoreboard — which ideas survive</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="sub">{t["born"]} candidates born · {t["promoted"]} promoted · '
                    f'{t["trial_complete"]} failed trial · {t["stale"]} stale · '
                    f'{t["demoted"]} demoted after promotion</div>', unsafe_allow_html=True)
        fams = [(k, v) for k, v in sb.get("families", {}).items()
                if v.get("survival_rate") is not None]
        if fams:
            st.markdown(table(["Idea family", "Born", "Survival", "Avg forward net"],
                [[k, v["born"], f'{v["survival_rate"] * 100:.0f}%', v.get("avg_forward_net", "—")]
                 for k, v in sorted(fams, key=lambda kv: -(kv[1]["survival_rate"] or 0))[:10]]),
                unsafe_allow_html=True)

    if lessons and lessons.get("variants"):
        st.markdown('<div class="sect">Shadow exits — the six roads not taken '
                    f'({lessons.get("n_trades", 0)} trades replayed)</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="sub">Base exit cumulative: {lessons.get("base_cum_R", 0)}R — '
                    f'variants below are what the SAME trades would have earned</div>',
                    unsafe_allow_html=True)
        st.markdown(table(["Exit variant", "Cum R", "Avg R", "Edge vs base", "Sample"],
            [[nm, v.get("cum_R", "—"), v.get("avg_R", "—"),
              f'{(v.get("edge_vs_base_R") or 0):+}R',
              f'{v["n"]} {"✓" if v.get("significant") else "(small)"}']
             for nm, v in sorted(lessons["variants"].items(),
                                 key=lambda kv: -(kv[1].get("cum_R") or 0))]),
            unsafe_allow_html=True)

    if watch:
        st.markdown('<div class="sect">Regime watch — daily trend per market</div>',
                    unsafe_allow_html=True)
        chips = ""
        for sym_k, w in sorted(watch.items()):
            reg = w.get("regime", "?") if isinstance(w, dict) else "?"
            col = GREEN if reg == "up" else (RED if reg == "down" else MUT)
            vol = ' · <span style="color:#fbbf24">VOL⚠</span>' if isinstance(w, dict) and w.get("vol_flag") else ""
            chips += (f'<div class="cc"><div class="nm">{sym_k}</div>'
                      f'<div class="bal" style="color:{col};font-size:.95rem">{reg.upper()}{vol}</div></div>')
        st.markdown(f'<div class="clist">{chips}</div>', unsafe_allow_html=True)

    if ledger:
        warns = []
        for nm, acct in ledger.items():
            if nm.startswith("_") or not isinstance(acct, dict):
                continue
            for rk, regs in acct.items():
                for rg, b in regs.items():
                    if isinstance(b, dict) and b.get("n", 0) >= 10 and b.get("net", 0) < 0:
                        warns.append([nm, rk, rg, b["n"], money(b["net"]), f'{b.get("win", 0) * 100:.0f}%'])
        if warns:
            st.markdown('<div class="sect">Regime warnings — rule loses in this weather</div>',
                        unsafe_allow_html=True)
            st.markdown(table(["Account", "Rule", "Regime", "Trades", "Net", "Win"], warns),
                        unsafe_allow_html=True)

    if mistakes and mistakes.get("months"):
        real_months = [m for m in mistakes["months"] if m[:2] == "20"]
        mo_key = max(real_months) if real_months else max(mistakes["months"].keys())
        mo = mistakes["months"][mo_key]
        st.markdown(f'<div class="sect">Mistake diary — {mo_key} '
                    f'({mo.get("trades", 0)} trades)</div>', unsafe_allow_html=True)
        rows = [["Exited too early (TP hit after exit)", mo.get("exited_too_early", 0)],
                ["Stop too tight (wider SL would have won)", mo.get("stop_too_tight", 0)],
                ["Held too long (time-exit at loss)", mo.get("held_too_long", 0)],
                ["Regime mismatch (bug guard)", mo.get("regime_mismatch", 0)],
                ["Data-feed skips", mo.get("feed_skips", 0)]]
        if mo.get("news_window_trades"):
            rows.append([f"Trades ±2h of high-impact news (net ${mo.get('news_window_net', 0)})",
                         mo["news_window_trades"]])
        if mo.get("neg_sentiment_trades"):
            rows.append([f"Trades during negative sentiment (net ${mo.get('neg_sentiment_net', 0)})",
                         mo["neg_sentiment_trades"]])
        st.markdown(table(["Mistake", "Count"], rows), unsafe_allow_html=True)

    if not any([hb, gate, cands, sb, lessons, watch, mistakes]):
        st.info("Brain state files is copy par abhi nahi bane — VPS dashboard live brain "
                "dikhata hai; GitHub copy weekly learning ke baad bharti hai.")

# ================= PER-COIN =================
else:
    k = next(kk for kk, lbl, *_ in ACCOUNTS if lbl == page)
    lbl, color, gl, sym = ACC[k]
    s = states[k] or {}
    a = stats(s)
    last, chg = fetch_ticker(sym)
    reg = (watch.get("XAUUSD") if k == "gold" else watch.get(sym)) or {}
    rr = reg.get("regime", "—") if isinstance(reg, dict) else "—"
    rc = GREEN if rr == "up" else (RED if rr == "down" else MUT)

    st.markdown(f'<div class="chead"><div class="cic" style="background:{color}">{gl}</div>'
                f'<div><div class="cname">{lbl}</div>'
                f'<div class="csym">{("gold ≈ PAXG proxy" if k == "gold" else sym + " · Binance live")}'
                f' · regime <b style="color:{rc}">{rr.upper()}</b></div></div></div>',
                unsafe_allow_html=True)

    pc = GREEN if a["pnl"] > 0 else (RED if a["pnl"] < 0 else INK)
    price_tile = ""
    if last is not None:
        cc = GREEN if (chg or 0) >= 0 else RED
        arw = "▲" if (chg or 0) >= 0 else "▼"
        price_tile = (f'<div class="t span2"><div class="lab">Live price · {sym}</div>'
                      f'<div style="display:flex;align-items:baseline;gap:12px;margin-top:8px;flex-wrap:wrap">'
                      f'<span class="price" style="color:{color}">${last:,.4f}</span>'
                      f'<span class="chg" style="color:{cc}">{arw} {abs(chg):.2f}% 24h</span></div></div>')
    st.markdown(f"""
    <div class="bento" style="grid-auto-rows:auto;">
      {price_tile}
      <div class="t"><div class="lab">Balance</div><div class="val" style="color:{pc}">${a['balance']:,.2f}</div>
        <div class="small">{money(a['pnl'], 2)} realized</div></div>
      <div class="t"><div class="lab">Win rate</div><div class="val">{a['win'] * 100:.0f}%</div>
        <div class="small">{a['trades']} closed · {a['open']} open</div></div>
    </div>""", unsafe_allow_html=True)

    closed = s.get("closed", [])
    if closed:
        st.markdown('<div class="sect">Account equity</div>', unsafe_allow_html=True)
        st.altair_chart(equity(closed, color if color != "#8f9bb3" else BRAND), **_WIDE)

    op = s.get("open", [])
    if op:
        st.markdown('<div class="sect">Open positions</div>', unsafe_allow_html=True)
        st.markdown(table(["Symbol", "Dir", "Entry", "Stop", "Target", "Opened (PKT)"],
            [[p["symbol"], f'<span class="pill {p["direction"]}">{p["direction"].upper()}</span>',
              f'{p["entry"]:,.4f}', f'{p.get("sl", 0):,.4f}', f'{p.get("tp", 0):,.4f}',
              pkt(p["open_time"])] for p in op]), unsafe_allow_html=True)
    if closed:
        st.markdown('<div class="sect">Recent closed trades</div>', unsafe_allow_html=True)
        st.markdown(table(["Symbol", "Dir", "Result", "P&L", "Closed (PKT)"],
            [[t["symbol"], f'<span class="pill {t["direction"]}">{t["direction"].upper()}</span>',
              f'<span class="pill {t["outcome"]}">{t["outcome"].upper()}</span>',
              money(t["pnl"], 2), pkt(t["close_time"])]
             for t in reversed(closed[-15:])]), unsafe_allow_html=True)
    if not closed and not op:
        st.markdown('<div class="sub" style="margin-top:14px">Abhi koi trade nahi — bot sahi '
                    'mauqe ka intezar mein (regime / signal).</div>', unsafe_allow_html=True)

    st.markdown('<div class="sect">Live price chart</div>', unsafe_allow_html=True)
    rng = st.radio("range", ["24H", "7D", "30D"], horizontal=True, label_visibility="collapsed")
    interval, limit = {"24H": ("15m", 96), "7D": ("1h", 168), "30D": ("4h", 180)}[rng]
    kl = fetch_klines(sym, interval, limit)
    if kl is not None and len(kl):
        st.altair_chart(candles(kl), **_WIDE)
        st.caption(f"{sym} · {rng} · {interval} candles · Binance public data · PKT")
    else:
        st.info("Live chart abhi load nahi hua — Refresh karein.")

st.markdown('<div class="foot">⚠️ Paper trading (virtual $5,000 / account). Past ≠ future. '
            'Not financial advice. Prices: Binance public API. Times: PKT (UTC+5). '
            'Brain: always-on self-learning (observer-gated promotions only).</div>',
            unsafe_allow_html=True)
