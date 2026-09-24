import json, urllib.request, urllib.parse, time, math
import numpy as np

CG = "https://api.coingecko.com/api/v3"
HDR = {"Accept":"application/json","User-Agent":"Mozilla/5.0"}

IDS = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
    "FETUSD": "fetch-ai",
    "GRTUSD": "the-graph",
    "ALGUSD": "algorand",
    "SANUSD": "the-sandbox",
    "ICPUSD": "internet-computer",
    "ETCUSD": "ethereum-classic",
    "IMXUSD": "immutable-x",
    "NEOUSD": "neo",
    "LNKUSD": "chainlink",
    "UNIUSD": "uniswap",
    "AAVUSD": "aave",
    "BARUSD": "hedera-hashgraph",
    "NERUSD": "near",
    "VECUSD": "vechain",
    "XLMUSD": "stellar",
    "XTZUSD": "tezos",
    "DOGEUSD": "dogecoin",
    "AVAXUSD": "avalanche-2",
    "DOTUSD": "polkadot",
    "BNBUSD": "binancecoin",
    "LTCUSD": "litecoin",
    "XMRUSD": "monero",
    "DASHUSD": "dash",
}

def fetch_ohlc(cg_id):
    url = f"{CG}/coins/{cg_id}/ohlc?vs_currency=usd&days=90"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            data = json.loads(r.read())
        return data
    except Exception as e:
        print("fetch err", cg_id, e)
        return None

def compute_metrics(ohlc):
    closes = np.array([c[4] for c in ohlc])
    highs = np.array([c[2] for c in ohlc])
    lows = np.array([c[3] for c in ohlc])
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:14])
    avg_loss = np.mean(losses[:14])
    for i in range(14, len(gains)):
        avg_gain = (avg_gain * 13 + gains[i]) / 14
        avg_loss = (avg_loss * 13 + losses[i]) / 14
    rs = avg_gain / avg_loss if avg_loss != 0 else 100
    rsi = float(100 - 100/(1+rs))
    mu = float(np.mean(closes))
    sigma = float(np.std(closes, ddof=1))
    z = (closes[-1] - mu) / sigma if sigma > 0 else 0.0
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    atr = float(np.mean(trs[:14])) if len(trs) >= 14 else None
    atr_pct = (atr / closes[-1]) if atr else None
    chg_24h = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else None
    sma20 = float(np.mean(closes[-20:]))
    sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
    trend = "up" if sma20 > (sma50 or sma20) else "down"
    return {"rsi": rsi, "z": z, "atr_pct": atr_pct, "chg_24h": chg_24h, "trend": trend, "price": float(closes[-1])}

def score(m):
    base = 50.0
    if m["z"] <= -2: base += 5
    elif m["z"] <= -1.5: base += 2
    if m["rsi"] < 35: base += 15
    elif m["rsi"] < 40: base += 10
    if m["chg_24h"] is not None and m["chg_24h"] < -4: base += 10
    elif m["chg_24h"] is not None and m["chg_24h"] < -2: base += 5
    if m["trend"] == "down": base += 5
    if m["atr_pct"] is not None and 0.01 < m["atr_pct"] < 0.05: base += 5
    return max(0, min(100, base))

results = []
for sym, cg_id in IDS.items():
    ohlc = fetch_ohlc(cg_id)
    if not ohlc or len(ohlc) < 50:
        print("skip", sym, "bars", len(ohlc) if ohlc else 0)
        continue
    m = compute_metrics(ohlc)
    m["symbol"] = sym
    results.append(m)
    time.sleep(0.3)

for m in results:
    m["score"] = score(m)
    print(f"{m['symbol']} price={m['price']:.6f} rsi={m['rsi']:.1f} z={m['z']:.2f} chg={m['chg_24h']:.2f}% trend={m['trend']} score={m['score']:.1f}")

print("\n--- TOP SCORES >= 60 ---")
for m in sorted([r for r in results if r["score"]>=60], key=lambda x: x["score"], reverse=True):
    print(f"{m['symbol']} score={m['score']:.1f} rsi={m['rsi']:.1f} chg={m['chg_24h']:.2f}% price={m['price']:.6f} z={m['z']:.2f}")
