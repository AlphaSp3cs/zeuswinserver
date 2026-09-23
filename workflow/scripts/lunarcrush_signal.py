"""LunarCrush Social Sentiment Module — OuroTaurus overlay.
Fetches social velocity, sentiment score, and market impact for crypto assets.
"""
import requests
import time

BASE = "https://api.lunarcrush.com/v3"

ASSET_MAP = {
    "BTCUSD": "bitcoin",
    "ETHUSD": "ethereum",
    "SOLUSD": "solana",
    "XRPUSD": "ripple",
    "ADAUSD": "cardano",
    "DOTUSD": "polkadot",
    "AVAXUSD": "avalanche-2",
    "LINKUSD": "chainlink",
    "UNIUSD": "uniswap",
    "MATICUSD": "polygon-ecosystem-token",
    "ATOMUSD": "cosmos",
    "NEARUSD": "near",
    "ALGOUSD": "algorand",
    "TAOUSD": "bittensor",
    "FILUSD": "filecoin",
    "INJUSD": "injective-protocol",
    "RUNEUSD": "thorchain",
    "AAVEUSD": "aave",
    "GRTUSD": "the-graph",
    "APTUSD": "aptos",
}

def fetch_social(symbol):
    coin_id = ASSET_MAP.get(symbol)
    if not coin_id:
        return None
    try:
        url = f"{BASE}/coins"
        params = {"symbol": coin_id, "fields": "symbol,name,social_score,sentiment,social_velocity,market_data"}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        coins = data.get("data", {}).get("coins", [])
        if not coins:
            return None
        c = coins[0]
        return {
            "symbol": symbol,
            "social_score": c.get("social_score", 0),
            "sentiment": c.get("sentiment", "neutral"),
            "social_velocity": c.get("social_velocity", 0),
            "name": c.get("name", coin_id),
        }
    except Exception:
        return None

def scan_universe():
    results = []
    for sym in ASSET_MAP:
        r = fetch_social(sym)
        if r:
            results.append(r)
        time.sleep(0.5)
    return results

if __name__ == "__main__":
    print("LunarCrush Social Sentiment Scan")
    print("=" * 50)
    data = scan_universe()
    data.sort(key=lambda x: x.get("social_score", 0), reverse=True)
    for d in data[:15]:
        sent = d.get("sentiment", "neutral")
        score = d.get("social_score", 0)
        vel = d.get("social_velocity", 0)
        print(f"{d['symbol']:10s} score={score:5.0f} sentiment={sent:10s} velocity={vel:5.0f}")
    print(f"\nTotal: {len(data)} assets scanned")