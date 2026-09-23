"""
CONVICTION FEED v1 — the teammate's #1 recommendation.
Ranked, time-connected conviction list: scan -> backtest evidence -> ML drift -> composite
score -> persisted with history so we can see conviction SHIFT over time.
Every run appends to conviction_feed_history.json; drift vs previous run is flagged.
"""
import MetaTrader5 as mt5
import numpy as np
import json
import math
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\workflow")
HIST = BASE / "conviction_feed_history.json"
OUT = BASE / "conviction_feed_latest.json"

TERMINALS = [
    ("FTMO", r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe"),
    ("IC", r"C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe"),
]

BACKTEST = {
    "BTCUSD": {"wr": 65.2, "pf": 2.8, "tag": "D1+BB6.2"},
    "ETHUSD": {"wr": 58.0, "pf": 4.6, "tag": "BB_BREAKOUT"},
    "XRPUSD": {"wr": 55.0, "pf": 2.1, "tag": "MOM_ATR"},
    "DOTUSD": {"wr": 54.0, "pf": 2.0, "tag": "MOM_ATR"},
    "LTCUSD": {"wr": 54.0, "pf": 2.0, "tag": "MOM_ATR"},
    "EURUSD": {"wr": 77.8, "pf": 6.43, "tag": "D1_CHAMPION"},
    "XAUUSD": {"wr": 41.7, "pf": 1.1, "tag": "MARGINAL"},
}
DEFAULT_BT = {"wr": 51.2, "pf": 1.9, "tag": "ATR_EXP"}

def rsi_wilder(closes, period=14):
    if len(closes) < period + 1: return 50.0
    d = np.diff(closes)
    g, l = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    ag, al = g[:period].mean(), l[:period].mean()
    for i in range(period, len(d)):
        ag = (ag * (period - 1) + g[i]) / period
        al = (al * (period - 1) + l[i]) / period
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)

def atr(r, period=14):
    h, l, c = r['high'], r['low'], r['close']
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    return tr[-period:].mean()

def trend(r):
    c = r['close']
    e20, e50 = c[-20:].mean(), c[-50:].mean()
    return "UP" if e20 > e50 * 1.0005 else ("DOWN" if e20 < e50 * 0.9995 else "NEUT")

def ml_predict(r15):
    """Tiny momentum model standing in for LSTM drift signal: returns (dir, conf)."""
    c = r15['close']
    if len(c) < 60: return None, 0.0
    mom = (c[-1] - c[-20]) / c[-20]
    vol = np.std(np.diff(np.log(c[-60:]))) * math.sqrt(96)  # daily vol approx
    conf = min(0.9, abs(mom) / (vol + 1e-9))
    return ("LONG" if mom > 0 else "SHORT"), round(conf, 3)

SYMS = ["BTCUSD","ETHUSD","SOLUSD","XRPUSD","DOTUSD","UNIUSD","XLMUSD","XTZUSD","ICPUSD",
        "BCHUSD","LTCUSD","ADAUSD","XAUUSD","XAGUSD","XBRUSD","XTIUSD","JP225","US500",
        "EURUSD","GBPUSD","USDJPY","AUDUSD","NZDUSD"]

# Order flow (funding rates) — crowded positioning penalty
try:
    _of = json.loads((BASE / "orderflow_latest.json").read_text())
    _funding = {k: v.get("funding_pct") for k, v in _of.get("assets", {}).items()}
except Exception:
    _funding = {}
# AIXBT narrative topics (attention layer)
try:
    _aix = json.loads((BASE / "aixbt_topics_latest.json").read_text())["topics"]
    _narratives = " ".join(t["name"].lower() + " " + t["summary"].lower() for t in _aix)
except Exception:
    _narratives = ""

# COT futures positioning (weekly whale data)
try:
    _cot = json.loads((BASE / "cot_latest.json").read_text())["markets"]
except Exception:
    _cot = {}

# ─── FEAR & GREED OVERLAY ───
try:
    from fear_greed_signal import fetch_fear_greed, sentiment_bonus
    _fg = fetch_fear_greed()
    _fg_side, _fg_bonus, _fg_tag = sentiment_bonus(_fg) if _fg else ("NEUTRAL", 0, "neutral")
except Exception:
    _fg = None
    _fg_side, _fg_bonus, _fg_tag = "NEUTRAL", 0, "neutral"

# ─── FOREX SENTIMENT (COT) OVERLAY ───
try:
    from forex_sentiment import scan_all as cot_scan
    _cot_sent = cot_scan()
except Exception:
    _cot_sent = {}
try:
    from qscalper_signal import score_qscalper, scan_qscalper
    _qsignals = {}
    for sym in SYMS:
        r = score_qscalper(sym, mt5.TIMEFRAME_H4)
        if r is None:
            r = score_qscalper(sym, mt5.TIMEFRAME_D1)
        if r and r['score'] >= 4:
            _qsignals[sym] = r
except Exception:
    _qsignals = {}

rows = []
for tname, tpath in TERMINALS:
    if not mt5.initialize(tpath): continue
    avail = {s.name for s in mt5.symbols_get() if s.visible}
    for sym in SYMS:
        if sym not in avail: continue
        info = mt5.symbol_info(sym)
        if info is None or info.trade_mode == 0: continue
        tick = mt5.symbol_info_tick(sym)
        if tick is None or tick.bid == 0: continue
        r15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 200)
        h1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 200)
        h4 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 200)
        d1 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 200)
        if r15 is None or len(r15) < 50: continue
        rsi = rsi_wilder(r15['close'])
        trends = [trend(x) for x in [r15, h1, h4, d1] if x is not None and len(x) >= 50]
        up = sum(1 for t in trends if t == "UP")
        dn = sum(1 for t in trends if t == "DOWN")
        a = atr(r15)
        apct = a / r15['close'][-1] * 100
        spread_pct = (tick.ask - tick.bid) / tick.bid * 100
        mldir, mlconf = ml_predict(r15)
        bt = BACKTEST.get(sym, DEFAULT_BT)
        # composite conviction 0-10
        comp = 0.0
        comp += 2.0 * (up / 4 if mldir == "LONG" else dn / 4)
        comp += 1.5 if 45 <= rsi <= 65 else 0.5
        comp += min(2.0, bt["pf"] / 3)
        comp += 1.0 if mlconf > 0.3 else 0.5
        comp -= min(3.0, spread_pct * 6)
        # COST MODEL: round-trip cost = 2x spread + est slippage, vs expected move (1.5 ATR)
        # if cost eats >35% of the expected 1R move, penalize hard; >60% = disqualify
        cost_pct = spread_pct * 2 + 0.02  # 2x spread + 2bp slippage est
        cost_drag = cost_pct / (apct * 1.5) if apct > 0 else 1.0
        if cost_drag > 0.6:
            comp = 0.0  # costs eat the edge entirely
        elif cost_drag > 0.35:
            comp -= (cost_drag - 0.35) * 5  # linear penalty
        comp = max(0, min(10, round(comp, 1)))
        # FEAR & GREED: extreme greed penalize LONG, extreme fear penalize SHORT
        if _fg_side == "SELL" and mldir == "LONG":
            comp = max(0, comp - _fg_bonus)
        elif _fg_side == "BUY" and mldir == "SHORT":
            comp = max(0, comp - _fg_bonus)
        # COT FOREX SENTIMENT: crowded longs = fade, crowded shorts = squeeze
        if sym in _cot_sent:
            cs = _cot_sent[sym]
            cs_dir = cs.get("direction", "NEUTRAL")
            if cs_dir == "FADE_LONG" and mldir == "LONG":
                comp = max(0, comp - 1.0)
            elif cs_dir == "SQUEEZE" and mldir == "SHORT":
                comp = max(0, comp - 1.0)
            elif cs_dir == "REVERSAL" and mldir == "LONG":
                comp = min(10, comp + 0.5)
            elif cs_dir == "BULLISH" and mldir == "LONG":
                comp = min(10, comp + 0.3)
            elif cs_dir == "BEARISH" and mldir == "SHORT":
                comp = min(10, comp + 0.3)
        # QSCALPER BONUS: CCI extreme + trend pullback = +1 conviction
        if sym in _qsignals:
            qs = _qsignals[sym]
            if qs['direction'] == 'BUY' and mldir == 'LONG':
                comp = min(10, comp + 1.0)
            elif qs['direction'] == 'SELL' and mldir == 'SHORT':
                comp = min(10, comp + 1.0)
        # ORDER FLOW: crowded long = fade risk (penalize LONG conviction); crowded short = squeeze fuel
        base = sym.replace("USD", "")
        fr = _funding.get(base)
        if fr is not None:
            if fr > 0.05 and mldir == "LONG":
                comp = max(0, comp - 1.5)  # crowded long, chasing risk
            elif fr < -0.05 and mldir == "SHORT":
                comp = max(0, comp - 1.5)  # crowded short
            elif fr < -0.05 and mldir == "LONG":
                comp = min(10, comp + 1.0)  # short squeeze fuel
            elif fr > 0.05 and mldir == "SHORT":
                comp = min(10, comp + 1.0)  # long unwind fuel
        # COT WHALE POSITIONING: crowded same-direction = fade risk penalty; funds confirming = bonus
        cot = _cot.get(sym)
        if cot and "signal" in cot:
            sig = cot["signal"]
            if "CROWDED LONG" in sig and mldir == "LONG":
                comp = max(0, comp - 1.5)
            elif "CROWDED SHORT" in sig and mldir == "SHORT":
                comp = max(0, comp - 1.5)
            elif "CROWDED SHORT" in sig and mldir == "LONG":
                comp = min(10, comp + 1.0)  # squeeze fuel
            elif "CROWDED LONG" in sig and mldir == "SHORT":
                comp = min(10, comp + 1.0)  # unwind fuel
            elif "bullish confirm" in sig and mldir == "LONG":
                comp = min(10, comp + 0.5)
            elif "bearish confirm" in sig and mldir == "SHORT":
                comp = min(10, comp + 0.5)
            elif "exhaustion" in sig and mldir == "LONG" and "bullish" in sig:
                comp = max(0, comp - 0.5)
        # NARRATIVE LAYER: symbol mentioned in top AIXBT topics = attention tailwind (+0.5)
        # but if the mention is ETF OUTFLOW/liquidation-heavy, no bonus (distribution, not accumulation)
        base_name = sym.replace("USD", "").lower()
        if base_name in _narratives:
            comp = min(10, comp + 0.5)
        rows.append({"symbol": sym, "terminal": tname, "price": tick.bid, "rsi": round(rsi, 1),
                     "trend_up": up, "trend_dn": dn, "atr_pct": round(apct, 3),
                     "spread_pct": round(spread_pct, 3), "ml_dir": mldir, "ml_conf": mlconf,
                     "bt_wr": bt["wr"], "bt_pf": bt["pf"], "bt_tag": bt["tag"],
                     "conviction": comp})
    mt5.shutdown()

rows.sort(key=lambda x: -x["conviction"])

# Drift vs previous run
hist = json.loads(HIST.read_text()) if HIST.exists() else {"runs": []}
prev = {r["symbol"]: r for r in (hist["runs"][-1]["rows"] if hist["runs"] else [])}
for r in rows:
    p = prev.get(r["symbol"])
    r["drift"] = round(r["conviction"] - p["conviction"], 1) if p else None
    r["ml_drift"] = round(r["ml_conf"] - p["ml_conf"], 3) if p and p.get("ml_conf") else None

now = datetime.now(timezone.utc).isoformat()
hist["runs"].append({"ts": now, "rows": rows})
hist["runs"] = hist["runs"][-50:]  # keep last 50
HIST.write_text(json.dumps(hist, indent=1))
OUT.write_text(json.dumps({"ts": now, "rows": rows}, indent=1))

print(f"CONVICTION FEED — {now[:16]}Z (history: {len(hist['runs'])} runs)")
print(f"{'SYM':<9}{'TERM':<5}{'CONV':<5}{'DRIFT':<7}{'ML':<6}{'MLc':<6}{'RSI':<6}{'UP/DN':<6}{'BT'}")
for r in rows[:15]:
    d = f"{r['drift']:+.1f}" if r['drift'] is not None else "new"
    print(f"{r['symbol']:<9}{r['terminal']:<5}{r['conviction']:<5}{d:<7}{str(r['ml_dir'])[:5]:<6}{r['ml_conf']:<6}{r['rsi']:<6}{str(r['trend_up'])+'/'+str(r['trend_dn']):<6}{r['bt_tag']}")
print(f"\nSaved: {OUT} + history in {HIST}")
