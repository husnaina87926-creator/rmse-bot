# RMSE_BOT Core Engine + Backtester — Implementation Plan (Plan 1 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Roman Urdu note:** Yeh Plan 1 sirf **dimaag aur backtester** banata hai — koi Telegram/dashboard/deploy nahi. Maqsad: strategy ko purane data pe chala kar dekhna ke yeh profitable hai ya nahi, **bina ek rupya khoye**. Sab code assistant likhega; har step test ke saath.

**Goal:** Build a testable Python analysis engine (indicators + market structure + risk) that generates trade signals, plus a backtester that runs it on historical Forex/Gold data and reports proper metrics.

**Architecture:** Pure functions over pandas DataFrames. Each module has one responsibility and is unit-tested with deterministic synthetic data. The same `signal_engine` and `risk` modules are designed for reuse by later live/auto-trade plans. AI-vision is a stubbed hook now, implemented in Plan 2.

**Tech Stack:** Python 3.11+, pandas, numpy, PyYAML, yfinance (historical data), pytest. Indicators implemented manually (no TA-lib dependency) for testability.

**Plan roadmap (context):**
- **Plan 1 (this):** Core engine + backtester — prove the strategy
- **Plan 2:** chart_render + ai_vision (Gemini) + session/news/volatility filters
- **Plan 3:** Telegram alerts + storage + `main.py` + GitHub Actions deploy
- **Plan 4:** Streamlit dashboard

---

## File Structure

```
RMSE_BOT/
  rmse_bot/
    __init__.py
    config.py          # load_config() -> dict
    data_feed.py       # load_csv(), fetch_yfinance() -> OHLC DataFrame
    indicators.py      # ema(), rsi(), atr()
    structure.py       # find_swings(), classify_trend(), detect_bos()
    risk.py            # position_size(), trade_cost()
    signal_engine.py   # Signal dataclass, generate_signal()
    backtest.py        # backtest(), BacktestResult, metrics
  tests/
    test_indicators.py
    test_structure.py
    test_risk.py
    test_signal_engine.py
    test_backtest.py
  scripts/
    run_backtest.py    # integration: fetch real data, print report
  config.yaml
  requirements.txt
  pytest.ini
  README.md
```

**Canonical OHLC DataFrame** (used everywhere): columns `time` (datetime64), `open`, `high`, `low`, `close` (float). Sorted ascending by time, default integer index.

**Canonical signatures (keep consistent across tasks):**
- `load_config(path="config.yaml") -> dict`
- `ema(series: pd.Series, period: int) -> pd.Series`
- `rsi(close: pd.Series, period: int = 14) -> pd.Series`
- `atr(df: pd.DataFrame, period: int = 14) -> pd.Series`
- `load_csv(path: str) -> pd.DataFrame`
- `fetch_yfinance(symbol: str, interval: str, period: str) -> pd.DataFrame`
- `find_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame`  (adds bool cols `swing_high`, `swing_low`)
- `classify_trend(df: pd.DataFrame, ema_period: int = 200) -> str`  (`"up"|"down"|"range"`)
- `detect_bos(df: pd.DataFrame) -> str`  (`"bullish"|"bearish"|"none"`)
- `position_size(balance, risk_pct, entry, stop, contract_size) -> float`  (lots)
- `trade_cost(lots, cfg_instrument) -> float`  ($ cost)
- `Signal(direction, entry, sl, tp, confidence, reason, time)` dataclass; `direction in {"buy","sell"}`
- `generate_signal(df_1h, df_15m, cfg) -> Signal | None`
- `backtest(df_15m, df_1h, cfg) -> BacktestResult`

---

### Task 0: Project scaffold

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `rmse_bot/__init__.py`, `tests/__init__.py`, `config.yaml`

- [ ] **Step 1: Create `requirements.txt`**

```
pandas>=2.0
numpy>=1.24
PyYAML>=6.0
yfinance>=0.2.40
pytest>=8.0
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 3: Create empty packages**

`rmse_bot/__init__.py` and `tests/__init__.py` — both empty files.

- [ ] **Step 4: Create `config.yaml`**

```yaml
account:
  size_usd: 100
  risk_per_trade_pct: 1.0
risk:
  reward_ratio: 2.0
  atr_period: 14
  sl_atr_mult: 1.5
signal:
  confidence_threshold: 70
  ema_fast: 9
  ema_slow: 21
  ema_trend: 200
  rsi_period: 14
instruments:
  XAUUSD:
    contract_size: 100        # oz per 1.0 lot
    spread_price: 0.30        # price units (USD)
    slippage_price: 0.10
    commission_per_lot: 0.0
    yf_symbol: "GC=F"         # gold futures proxy for backtest
  EURUSD:
    contract_size: 100000
    spread_price: 0.00010
    slippage_price: 0.00005
    commission_per_lot: 3.5
    yf_symbol: "EURUSD=X"
```

- [ ] **Step 5: Set up venv and install**

Run:
```bash
cd /Users/mirzahusnain/Downloads/RMSE_BOT
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```
Expected: `no tests ran` (or collected 0 items) — confirms pytest works.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini rmse_bot/ tests/ config.yaml
git commit -m "chore: project scaffold for RMSE_BOT core engine"
```

---

### Task 1: Config loader

**Files:**
- Create: `rmse_bot/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test** (`tests/test_config.py`)

```python
from rmse_bot.config import load_config

def test_load_config_reads_account_defaults():
    cfg = load_config("config.yaml")
    assert cfg["account"]["size_usd"] == 100
    assert cfg["account"]["risk_per_trade_pct"] == 1.0
    assert cfg["instruments"]["XAUUSD"]["contract_size"] == 100
```

- [ ] **Step 2: Run, verify fail**

Run: `pytest tests/test_config.py -v` → FAIL (ModuleNotFoundError: rmse_bot.config).

- [ ] **Step 3: Implement** (`rmse_bot/config.py`)

```python
import yaml

def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)
```

- [ ] **Step 4: Run, verify pass** — `pytest tests/test_config.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add rmse_bot/config.py tests/test_config.py
git commit -m "feat: config loader"
```

---

### Task 2: Indicators — EMA

**Files:**
- Create: `rmse_bot/indicators.py`
- Test: `tests/test_indicators.py`

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
from rmse_bot.indicators import ema

def test_ema_first_value_equals_first_price():
    s = pd.Series([10, 11, 12, 13, 14], dtype=float)
    out = ema(s, period=3)
    assert round(out.iloc[0], 6) == 10.0          # seeded with first value

def test_ema_known_value():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = ema(s, period=2)
    # alpha = 2/(2+1)=0.6667; ema2 = 1; then 0.6667*2+0.3333*1=1.6667
    assert round(out.iloc[1], 4) == 1.6667
```

- [ ] **Step 2: Run, verify fail** — `pytest tests/test_indicators.py::test_ema_known_value -v` → FAIL

- [ ] **Step 3: Implement** (append to `rmse_bot/indicators.py`)

```python
import pandas as pd

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()
```

- [ ] **Step 4: Run, verify pass** — `pytest tests/test_indicators.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add rmse_bot/indicators.py tests/test_indicators.py
git commit -m "feat: EMA indicator"
```

---

### Task 3: Indicators — RSI

**Files:** Modify `rmse_bot/indicators.py`; modify `tests/test_indicators.py`

- [ ] **Step 1: Add failing test**

```python
from rmse_bot.indicators import rsi

def test_rsi_all_gains_is_100():
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], dtype=float)
    out = rsi(s, period=14)
    assert round(out.iloc[-1], 1) == 100.0

def test_rsi_in_bounds():
    s = pd.Series([5, 4, 6, 3, 7, 2, 8, 1, 9, 5, 6, 4, 7, 3, 8, 6], dtype=float)
    out = rsi(s, period=14)
    assert 0 <= out.iloc[-1] <= 100
```

- [ ] **Step 2: Run, verify fail** → FAIL (rsi not defined)

- [ ] **Step 3: Implement** (append to `indicators.py`)

```python
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))
```

- [ ] **Step 4: Run, verify pass** → PASS

- [ ] **Step 5: Commit** — `git commit -am "feat: RSI indicator"`

---

### Task 4: Indicators — ATR

**Files:** Modify `rmse_bot/indicators.py`; modify `tests/test_indicators.py`

- [ ] **Step 1: Add failing test**

```python
from rmse_bot.indicators import atr

def test_atr_constant_range():
    # every candle has high-low = 2, no gaps -> ATR should converge to 2
    df = pd.DataFrame({
        "high":  [12, 13, 14, 15, 16],
        "low":   [10, 11, 12, 13, 14],
        "close": [11, 12, 13, 14, 15],
    }, dtype=float)
    out = atr(df, period=3)
    assert round(out.iloc[-1], 4) == 2.0
```

- [ ] **Step 2: Run, verify fail** → FAIL

- [ ] **Step 3: Implement** (append to `indicators.py`)

```python
def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()
```

- [ ] **Step 4: Run, verify pass** → PASS

- [ ] **Step 5: Commit** — `git commit -am "feat: ATR indicator"`

---

### Task 5: Data feed (CSV + yfinance)

**Files:**
- Create: `rmse_bot/data_feed.py`
- Test: `tests/test_data_feed.py` (+ fixture CSV)

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
from rmse_bot.data_feed import load_csv, normalize_ohlc

def test_normalize_lowercases_and_sorts():
    raw = pd.DataFrame({
        "Time": pd.to_datetime(["2024-01-02", "2024-01-01"]),
        "Open": [2.0, 1.0], "High": [3.0, 2.0],
        "Low": [1.0, 0.5], "Close": [2.5, 1.5],
    })
    out = normalize_ohlc(raw)
    assert list(out.columns) == ["time", "open", "high", "low", "close"]
    assert out["close"].iloc[0] == 1.5  # sorted ascending by time

def test_load_csv(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("time,open,high,low,close\n2024-01-01,1,2,0.5,1.5\n")
    df = load_csv(str(p))
    assert df["high"].iloc[0] == 2.0
```

- [ ] **Step 2: Run, verify fail** → FAIL

- [ ] **Step 3: Implement** (`rmse_bot/data_feed.py`)

```python
import pandas as pd

REQUIRED = ["time", "open", "high", "low", "close"]

def normalize_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: c.lower() for c in df.columns})
    df["time"] = pd.to_datetime(df["time"])
    df = df[REQUIRED].sort_values("time").reset_index(drop=True)
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    return df

def load_csv(path: str) -> pd.DataFrame:
    return normalize_ohlc(pd.read_csv(path))

def fetch_yfinance(symbol: str, interval: str, period: str) -> pd.DataFrame:
    import yfinance as yf
    raw = yf.download(symbol, interval=interval, period=period,
                      progress=False, auto_adjust=False)
    raw = raw.reset_index()
    raw.columns = [c[0] if isinstance(c, tuple) else c for c in raw.columns]
    raw = raw.rename(columns={"Date": "time", "Datetime": "time"})
    return normalize_ohlc(raw)
```

- [ ] **Step 4: Run, verify pass** → PASS (yfinance not called in unit tests)

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: data feed (csv + yfinance)"`

---

### Task 6: Structure — swing detection

**Files:**
- Create: `rmse_bot/structure.py`
- Test: `tests/test_structure.py`

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
from rmse_bot.structure import find_swings

def test_find_swings_marks_local_extremes():
    # index 2 is a clear swing high (14), index 5 a swing low (8)
    df = pd.DataFrame({
        "high":  [10, 12, 14, 12, 10, 9,  11, 13],
        "low":   [9,  11, 13, 11, 9,  8,  10, 12],
        "close": [9.5,11.5,13.5,11.5,9.5,8.5,10.5,12.5],
    }, dtype=float)
    out = find_swings(df, left=2, right=2)
    assert bool(out["swing_high"].iloc[2]) is True
    assert bool(out["swing_low"].iloc[5]) is True
    assert bool(out["swing_high"].iloc[0]) is False  # edges can't be swings
```

- [ ] **Step 2: Run, verify fail** → FAIL

- [ ] **Step 3: Implement** (`rmse_bot/structure.py`)

```python
import pandas as pd

def find_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> pd.DataFrame:
    out = df.copy()
    n = len(df)
    sh = [False] * n
    sl = [False] * n
    for i in range(left, n - right):
        window_h = df["high"].iloc[i - left:i + right + 1]
        window_l = df["low"].iloc[i - left:i + right + 1]
        if df["high"].iloc[i] == window_h.max() and (window_h == df["high"].iloc[i]).sum() == 1:
            sh[i] = True
        if df["low"].iloc[i] == window_l.min() and (window_l == df["low"].iloc[i]).sum() == 1:
            sl[i] = True
    out["swing_high"] = sh
    out["swing_low"] = sl
    return out
```

- [ ] **Step 4: Run, verify pass** → PASS

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: swing detection"`

---

### Task 7: Structure — trend classification

**Files:** Modify `rmse_bot/structure.py`; modify `tests/test_structure.py`

- [ ] **Step 1: Add failing test**

```python
from rmse_bot.structure import classify_trend

def _ramp(start, step, n):
    import pandas as pd
    vals = [start + step * i for i in range(n)]
    return pd.DataFrame({"high": [v + 0.5 for v in vals],
                         "low": [v - 0.5 for v in vals],
                         "close": vals}, dtype=float)

def test_uptrend_when_price_above_rising_ema():
    df = _ramp(100, 1, 250)      # steadily rising
    assert classify_trend(df, ema_period=200) == "up"

def test_downtrend_when_price_below_falling_ema():
    df = _ramp(300, -1, 250)     # steadily falling
    assert classify_trend(df, ema_period=200) == "down"
```

- [ ] **Step 2: Run, verify fail** → FAIL

- [ ] **Step 3: Implement** (append to `structure.py`)

```python
from rmse_bot.indicators import ema

def classify_trend(df: pd.DataFrame, ema_period: int = 200) -> str:
    e = ema(df["close"], ema_period)
    price = df["close"].iloc[-1]
    slope = e.iloc[-1] - e.iloc[max(0, len(e) - 10)]
    if price > e.iloc[-1] and slope > 0:
        return "up"
    if price < e.iloc[-1] and slope < 0:
        return "down"
    return "range"
```

- [ ] **Step 4: Run, verify pass** → PASS

- [ ] **Step 5: Commit** — `git commit -am "feat: trend classification"`

---

### Task 8: Structure — Break of Structure (BOS)

**Files:** Modify `rmse_bot/structure.py`; modify `tests/test_structure.py`

- [ ] **Step 1: Add failing test**

```python
from rmse_bot.structure import detect_bos

def test_bullish_bos_when_close_breaks_last_swing_high():
    df = pd.DataFrame({
        "high":  [10, 12, 14, 12, 11, 13, 15.5],
        "low":   [9,  11, 13, 11, 10, 12, 14],
        "close": [9.5,11.5,13.5,11.5,10.5,12.5,15.2],  # last close 15.2 > swing high 14
    }, dtype=float)
    assert detect_bos(df) == "bullish"

def test_no_bos_when_range_bound():
    df = pd.DataFrame({
        "high":  [10, 12, 14, 12, 11, 13, 13.5],
        "low":   [9,  11, 13, 11, 10, 12, 12.5],
        "close": [9.5,11.5,13.5,11.5,10.5,12.5,13.0],
    }, dtype=float)
    assert detect_bos(df) == "none"
```

- [ ] **Step 2: Run, verify fail** → FAIL

- [ ] **Step 3: Implement** (append to `structure.py`)

```python
def detect_bos(df: pd.DataFrame) -> str:
    sw = find_swings(df, left=2, right=2)
    last_close = df["close"].iloc[-1]
    highs = sw.loc[sw["swing_high"], "high"]
    lows = sw.loc[sw["swing_low"], "low"]
    if not highs.empty and last_close > highs.iloc[-1]:
        return "bullish"
    if not lows.empty and last_close < lows.iloc[-1]:
        return "bearish"
    return "none"
```

- [ ] **Step 4: Run, verify pass** → PASS

- [ ] **Step 5: Commit** — `git commit -am "feat: break-of-structure detection"`

---

### Task 9: Risk — position sizing

**Files:**
- Create: `rmse_bot/risk.py`
- Test: `tests/test_risk.py`

- [ ] **Step 1: Write the failing test**

```python
from rmse_bot.risk import position_size

def test_position_size_basic():
    # balance 100, risk 1% = $1; SL distance 5 price units; contract 100 units/lot
    # lots = 1 / (5 * 100) = 0.002
    lots = position_size(balance=100, risk_pct=1.0, entry=2340, stop=2335, contract_size=100)
    assert round(lots, 6) == 0.002

def test_position_size_zero_distance_returns_zero():
    assert position_size(100, 1.0, 2340, 2340, 100) == 0.0
```

- [ ] **Step 2: Run, verify fail** → FAIL

- [ ] **Step 3: Implement** (`rmse_bot/risk.py`)

```python
def position_size(balance: float, risk_pct: float, entry: float,
                  stop: float, contract_size: float) -> float:
    risk_amount = balance * (risk_pct / 100.0)
    distance = abs(entry - stop)
    if distance == 0:
        return 0.0
    return risk_amount / (distance * contract_size)
```

- [ ] **Step 4: Run, verify pass** → PASS

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: position sizing"`

---

### Task 10: Risk — trade cost model

**Files:** Modify `rmse_bot/risk.py`; modify `tests/test_risk.py`

- [ ] **Step 1: Add failing test**

```python
from rmse_bot.risk import trade_cost

def test_trade_cost_combines_spread_slippage_commission():
    instr = {"contract_size": 100, "spread_price": 0.30,
             "slippage_price": 0.10, "commission_per_lot": 0.0}
    # (0.30 + 0.10) * 100 * 0.002 lots = 0.08 ; commission 0
    assert round(trade_cost(0.002, instr), 6) == 0.08
```

- [ ] **Step 2: Run, verify fail** → FAIL

- [ ] **Step 3: Implement** (append to `risk.py`)

```python
def trade_cost(lots: float, instr: dict) -> float:
    spread = instr.get("spread_price", 0.0)
    slippage = instr.get("slippage_price", 0.0)
    contract = instr["contract_size"]
    commission = instr.get("commission_per_lot", 0.0)
    return (spread + slippage) * contract * lots + commission * lots
```

- [ ] **Step 4: Run, verify pass** → PASS

- [ ] **Step 5: Commit** — `git commit -am "feat: trade cost model"`

---

### Task 11: Signal engine

**Files:**
- Create: `rmse_bot/signal_engine.py`
- Test: `tests/test_signal_engine.py`

The rule (Trend + Pullback, structure-led, indicators as confluence; AI-vision hook reserved for Plan 2):
1. `classify_trend(df_1h)` must be `"up"` (buy) or `"down"` (sell).
2. On 15m, EMA(fast) crosses EMA(slow) in trend direction on the last bar.
3. RSI confirms (buy: 50–70; sell: 30–50).
4. SL = entry ∓ `sl_atr_mult`×ATR; TP = entry ± `reward_ratio`×(entry−SL).
5. Confidence = 50 base + 20 if BOS agrees + 15 if RSI strong; clip to 100.

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
from rmse_bot.config import load_config
from rmse_bot.signal_engine import generate_signal, Signal

def _series(vals):
    return pd.DataFrame({"high": [v + 0.5 for v in vals],
                         "low":  [v - 0.5 for v in vals],
                         "close": vals,
                         "time": pd.date_range("2024-01-01", periods=len(vals), freq="15min")},
                        dtype="float64").assign(
        time=pd.date_range("2024-01-01", periods=len(vals), freq="15min"))

def test_no_signal_when_trend_range():
    cfg = load_config("config.yaml")
    flat = _series([100.0] * 250)
    assert generate_signal(flat, flat, cfg) is None

def test_buy_signal_in_uptrend_pullback():
    cfg = load_config("config.yaml")
    up = [100 + i * 0.5 for i in range(240)]
    up += [220, 219.5, 220.5, 222]   # small pullback then push up -> fast crosses slow up
    df = _series(up)
    sig = generate_signal(df, df, cfg)
    assert sig is not None
    assert sig.direction == "buy"
    assert sig.sl < sig.entry < sig.tp
```

- [ ] **Step 2: Run, verify fail** → FAIL

- [ ] **Step 3: Implement** (`rmse_bot/signal_engine.py`)

```python
from dataclasses import dataclass
import pandas as pd
from rmse_bot.indicators import ema, rsi, atr
from rmse_bot.structure import classify_trend, detect_bos

@dataclass
class Signal:
    direction: str   # "buy" | "sell"
    entry: float
    sl: float
    tp: float
    confidence: float
    reason: str
    time: pd.Timestamp

def _crossed_up(fast, slow):
    return fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]

def _crossed_down(fast, slow):
    return fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]

def generate_signal(df_1h: pd.DataFrame, df_15m: pd.DataFrame, cfg: dict) -> "Signal | None":
    s = cfg["signal"]; r = cfg["risk"]
    trend = classify_trend(df_1h, s["ema_trend"])
    if trend == "range":
        return None
    fast = ema(df_15m["close"], s["ema_fast"])
    slow = ema(df_15m["close"], s["ema_slow"])
    rsi_v = rsi(df_15m["close"], s["rsi_period"]).iloc[-1]
    a = atr(df_15m, r["atr_period"]).iloc[-1]
    entry = float(df_15m["close"].iloc[-1])
    bos = detect_bos(df_15m)
    t = df_15m["time"].iloc[-1] if "time" in df_15m else None

    if trend == "up" and _crossed_up(fast, slow) and 50 <= rsi_v <= 70:
        sl = entry - r["sl_atr_mult"] * a
        tp = entry + r["reward_ratio"] * (entry - sl)
        conf = 50 + (20 if bos == "bullish" else 0) + (15 if rsi_v >= 55 else 0)
        return Signal("buy", entry, sl, tp, min(conf, 100), f"uptrend+cross+rsi{rsi_v:.0f}+bos:{bos}", t)
    if trend == "down" and _crossed_down(fast, slow) and 30 <= rsi_v <= 50:
        sl = entry + r["sl_atr_mult"] * a
        tp = entry - r["reward_ratio"] * (sl - entry)
        conf = 50 + (20 if bos == "bearish" else 0) + (15 if rsi_v <= 45 else 0)
        return Signal("sell", entry, sl, tp, min(conf, 100), f"downtrend+cross+rsi{rsi_v:.0f}+bos:{bos}", t)
    return None
```

- [ ] **Step 4: Run, verify pass** → PASS (adjust the synthetic pullback values if cross doesn't trigger; the test documents intent)

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: signal engine (trend+pullback)"`

---

### Task 12: Backtester + metrics

**Files:**
- Create: `rmse_bot/backtest.py`
- Test: `tests/test_backtest.py`

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
from rmse_bot.backtest import simulate_trade, compute_metrics, BacktestResult

def test_simulate_trade_hits_tp():
    # buy entry 100, sl 95, tp 110; future highs reach 110 before low hits 95
    future = pd.DataFrame({"high": [101, 105, 111], "low": [99, 98, 109]}, dtype=float)
    outcome = simulate_trade("buy", entry=100, sl=95, tp=110, future=future)
    assert outcome == "tp"

def test_simulate_trade_hits_sl():
    future = pd.DataFrame({"high": [101, 102], "low": [99, 94]}, dtype=float)
    assert simulate_trade("buy", 100, 95, 110, future) == "sl"

def test_metrics_basic():
    trades = [{"pnl": 2.0}, {"pnl": 2.0}, {"pnl": -1.0}]
    m = compute_metrics(trades, start_balance=100)
    assert m["num_trades"] == 3
    assert round(m["win_rate"], 4) == round(2/3, 4)
    assert round(m["profit_factor"], 2) == 4.0     # gains 4 / losses 1
```

- [ ] **Step 2: Run, verify fail** → FAIL

- [ ] **Step 3: Implement** (`rmse_bot/backtest.py`)

```python
from dataclasses import dataclass, field
import pandas as pd
from rmse_bot.signal_engine import generate_signal
from rmse_bot.risk import position_size, trade_cost

@dataclass
class BacktestResult:
    trades: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

def simulate_trade(direction, entry, sl, tp, future: pd.DataFrame) -> str:
    for _, bar in future.iterrows():
        if direction == "buy":
            if bar["low"] <= sl:
                return "sl"
            if bar["high"] >= tp:
                return "tp"
        else:
            if bar["high"] >= sl:
                return "sl"
            if bar["low"] <= tp:
                return "tp"
    return "open"

def compute_metrics(trades: list, start_balance: float) -> dict:
    if not trades:
        return {"num_trades": 0, "win_rate": 0, "profit_factor": 0,
                "expectancy": 0, "max_drawdown": 0, "total_return": 0}
    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [-p for p in pnls if p < 0]
    gross_win, gross_loss = sum(wins), sum(losses)
    equity, peak, max_dd = start_balance, start_balance, 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "num_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
        "expectancy": sum(pnls) / len(trades),
        "max_drawdown": max_dd,
        "total_return": sum(pnls),
    }

def backtest(df_15m: pd.DataFrame, df_1h: pd.DataFrame, cfg: dict,
             instr: dict, lookback: int = 250) -> BacktestResult:
    balance = cfg["account"]["size_usd"]
    trades = []
    i = lookback
    while i < len(df_15m) - 1:
        window = df_15m.iloc[:i + 1]
        # align 1h context up to current 15m time
        h_ctx = df_1h[df_1h["time"] <= window["time"].iloc[-1]] if "time" in df_1h else df_1h
        if len(h_ctx) < cfg["signal"]["ema_trend"]:
            i += 1; continue
        sig = generate_signal(h_ctx, window, cfg)
        if sig is None:
            i += 1; continue
        future = df_15m.iloc[i + 1:i + 1 + 96]   # next ~24h of 15m bars
        outcome = simulate_trade(sig.direction, sig.entry, sig.sl, sig.tp, future)
        lots = position_size(balance, cfg["account"]["risk_per_trade_pct"],
                             sig.entry, sig.sl, instr["contract_size"])
        cost = trade_cost(lots, instr)
        if outcome == "tp":
            gross = abs(sig.tp - sig.entry) * instr["contract_size"] * lots
            pnl = gross - cost
        elif outcome == "sl":
            gross = -abs(sig.entry - sig.sl) * instr["contract_size"] * lots
            pnl = gross - cost
        else:
            i += 1; continue
        balance += pnl
        trades.append({"time": sig.time, "dir": sig.direction,
                       "outcome": outcome, "pnl": pnl, "balance": balance,
                       "confidence": sig.confidence, "reason": sig.reason})
        i += 96   # skip past the resolved trade window (no overlapping trades)
    res = BacktestResult(trades=trades,
                         metrics=compute_metrics(trades, cfg["account"]["size_usd"]))
    return res
```

- [ ] **Step 4: Run, verify pass** → PASS

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat: backtester + metrics"`

---

### Task 13: Integration — run backtest on real data

**Files:**
- Create: `scripts/run_backtest.py`

- [ ] **Step 1: Implement the script**

```python
"""Fetch real data via yfinance and run the backtest. Prints a metrics report.
Note: yfinance 15m history is limited (~60 days). For a full 2-3yr backtest we
plug a downloaded CSV in a later step; this proves the pipeline end-to-end."""
from rmse_bot.config import load_config
from rmse_bot.data_feed import fetch_yfinance
from rmse_bot.backtest import backtest

def main():
    cfg = load_config("config.yaml")
    for name, instr in cfg["instruments"].items():
        sym = instr["yf_symbol"]
        df15 = fetch_yfinance(sym, interval="15m", period="60d")
        df1h = fetch_yfinance(sym, interval="1h", period="730d")
        res = backtest(df15, df1h, cfg, instr)
        print(f"\n=== {name} ({sym}) ===")
        for k, v in res.metrics.items():
            print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `python scripts/run_backtest.py`
Expected: prints metrics blocks for XAUUSD and EURUSD (num_trades, win_rate, profit_factor, max_drawdown, total_return). Some instruments may show 0 trades on short windows — that's fine; the goal is a clean run.

- [ ] **Step 3: Commit** — `git add -A && git commit -m "feat: integration backtest runner"`

---

### Task 14: README + roadmap

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README** with: what RMSE_BOT is, Phase 1 vs 2, how to set up venv + install + run tests + run backtest, the 4-plan roadmap, and the honest caveats (no guaranteed profit; backtest decides; real money only after Plan 3 + demo). Link to the spec.

- [ ] **Step 2: Run full test suite**

Run: `pytest -q`
Expected: all tests PASS.

- [ ] **Step 3: Commit** — `git add -A && git commit -m "docs: README + roadmap"`

---

## Self-Review (completed)

- **Spec coverage:** Plan 1 covers spec §4 layers 1-2 (structure + indicators), §5 risk/realism (sizing + costs), §8 backtesting (metrics). Deferred to later plans (noted in roadmap): AI vision (§4 L3), filters (§4 L4), Telegram/storage/deploy (§6, §9), dashboard. Walk-forward (§8) → Plan 1 produces single-pass backtest; walk-forward added in Plan 1.5/Plan 2 once base metrics look sane.
- **Placeholder scan:** No TBD/TODO; every code step has runnable code.
- **Type consistency:** `Signal`, `generate_signal`, `position_size`, `trade_cost`, `backtest` signatures match across Tasks 9–13. DataFrame schema (`time/open/high/low/close`) consistent.
- **Known soft spot:** Task 11's synthetic pullback test may need value tuning so the EMA cross actually fires on the last bar — documented in the step; intent is fixed even if numbers are nudged.
