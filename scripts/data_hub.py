#!/usr/bin/env python3
"""
Zeus Data Hub v2 — Consolidated Market Intelligence Feed
7 sources: FRED macro, CoinGecko bulk, Yahoo futures, Twelve Data forex,
International equities, options gamma (algoxflow/zer0dte), Farside ETF flows.
All free APIs. No subscriptions. Keys optional (FRED, Twelve Data).
"""
import json, time, urllib.request, urllib.error, ssl, re
from datetime import datetime
from pathlib import Path

ROOT = Path("C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm")
CACHE_FILE = ROOT / "data_hub_cache.json"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_json(url: str, timeout: int = 10, headers: dict = None) -> dict:
    try:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "ZeusDataHub/2.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"_error": str(e)}

def fetch_html(url: str, timeout: int = 10) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return f"ERROR: {e}"

def fetch_yahoo(symbol: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    data = fetch_json(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    try:
        meta = data["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice", 0)
        prev = meta.get("chartPreviousClose", meta.get("previousClose", 0))
        chg = ((price - prev) / prev * 100) if prev else 0
        return {"symbol": symbol, "price": price, "change_24h": round(chg, 2), "source": "yahoo"}
    except Exception as e:
        return {"symbol": symbol, "_error": str(e)}

# ===== 1. FRED MACRO RATES =====
def fetch_fred_macro(fred_key: str = None) -> dict:
    """FRED: 10Y, 2Y, 30Y, SOFR, EFFR, HY OAS, TED, DXY."""
    result = {"source": "FRED", "timestamp": datetime.now().isoformat()}
    series = {
        "DGS2": "2Y", "DGS10": "10Y", "DGS30": "30Y",
        "SOFR": "SOFR", "EFFR": "EFFR",
        "BAMLH0A0HYM2": "HY_OAS", "TEDRATE": "TED",
        "DTWEXBGS": "DXY", "T10Y2Y": "T10Y2Y",
    }
    if not fred_key:
        result["note"] = "FRED key needed — free at fred.stlouisfed.org/apikey"
        result["series_ids"] = series
        return result
    for sid, name in series.items():
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={sid}&api_key={fred_key}&file_type=json&sort_order=desc&limit=1"
        data = fetch_json(url, timeout=10)
        try:
            obs = data["observations"][0]
            result[name] = {"value": obs["value"], "date": obs["date"]}
        except Exception as e:
            result[name] = {"_error": str(e)}
        time.sleep(0.2)
    return result

# ===== 2. COINGECKO BULK CRYPTO =====
def fetch_coingecko_bulk() -> dict:
    """20+ coins in 1 CoinGecko call."""
    ids = "bitcoin,ethereum,solana,ripple,zec,cardano,dogecoin,litecoin,polkadot,avalanche-2,matic-network,chainlink,uniswap,cosmos,arbitrum,filecoin,internet-computer,stellar,algorand,fantom,aptos,sui,near"
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"
    data = fetch_json(url, timeout=15)
    result = {"source": "coingecko", "timestamp": datetime.now().isoformat(), "coins": {}}
    cg_map = {
        "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "ripple": "XRP",
        "zcash": "ZEC", "cardano": "ADA", "dogecoin": "DOGE", "litecoin": "LTC",
        "polkadot": "DOT", "avalanche-2": "AVAX", "matic-network": "MATIC",
        "chainlink": "LINK", "uniswap": "UNI", "cosmos": "ATOM",
        "arbitrum": "ARB", "filecoin": "FIL", "internet-computer": "ICP",
        "stellar": "XLM", "algorand": "ALGO", "fantom": "FTM",
        "aptos": "APT", "sui": "SUI", "near": "NEAR",
    }
    for cid, sym in cg_map.items():
        if cid in data:
            d = data[cid]
            result["coins"][sym] = {
                "price": d.get("usd", 0),
                "change_24h": d.get("usd_24h_change", 0),
                "volume_24h": d.get("usd_24h_vol", 0),
            }
    return result

# ===== 3. YAHOO FUTURES — COMMODITIES + BONDS + INDICES =====
def fetch_yahoo_futures() -> list:
    """All major futures: energy, metals, bonds, indices, ags, livestock."""
    syms = {
        "CL=F": "WTI", "BZ=F": "Brent", "NG=F": "NatGas",
        "GC=F": "Gold", "SI=F": "Silver", "PL=F": "Platinum", "HG=F": "Copper",
        "ZB=F": "30Y", "ZN=F": "10Y", "ZF=F": "5Y", "ZT=F": "2Y",
        "ES=F": "SPX", "NQ=F": "Nasdaq", "YM=F": "Dow", "RTY=F": "Russell",
        "ZC=F": "Corn", "ZS=F": "Soybeans", "CT=F": "Cotton",
        "SB=F": "Sugar", "CC=F": "Cocoa", "KC=F": "Coffee",
        "LE=F": "LiveCattle", "HE=F": "LeanHogs",
    }
    results = []
    for sym, name in syms.items():
        data = fetch_yahoo(sym)
        data["name"] = name
        if "price" in data:
            results.append(data)
        time.sleep(0.15)
    return results

# ===== 4. FOREX (Yahoo — Twelve Data 404, Yahoo proven) =====
def fetch_forex_yahoo() -> list:
    """Forex via Yahoo (free, no key). Covers majors + EM."""
    pairs = {
        "EURUSD=X": "EUR/USD", "GBPUSD=X": "GBP/USD", "USDJPY=X": "USD/JPY",
        "USDCHF=X": "USD/CHF", "AUDUSD=X": "AUD/USD", "USDCAD=X": "USD/CAD",
        "USDTRY=X": "USD/TRY", "USDZAR=X": "USD/ZAR", "USDBRL=X": "USD/BRL",
        "USDMXN=X": "USD/MXN", "USDINR=X": "USD/INR", "USDKRW=X": "USD/KRW",
        "USDCNY=X": "USD/CNY", "USDRUB=X": "USD/RUB", "DX-Y.NYB": "DXY",
    }
    results = []
    for sym, name in pairs.items():
        data = fetch_yahoo(sym)
        data["name"] = name
        if "price" in data:
            results.append(data)
        time.sleep(0.15)
    return results

# ===== 5. INTERNATIONAL EQUITIES =====
def fetch_international_equities() -> list:
    """EU/Asia/LatAm equities via Yahoo."""
    syms = {
        "^STOXX50E": "EuroStoxx50", "^N225": "Nikkei225",
        "^HSI": "HangSeng", "000001.SS": "CSI300",
        "^KS11": "KOSPI", "^AXJO": "ASX200",
        "^FTSE": "FTSE100", "^GDAXI": "DAX", "^FCHI": "CAC40",
        "^IBOV": "Ibovespa", "^MXX": "IPC Mexico",
    }
    results = []
    for sym, name in syms.items():
        data = fetch_yahoo(sym)
        data["name"] = name
        if "price" in data:
            results.append(data)
        time.sleep(0.15)
    return results

# ===== 6. OPTIONS GAMMA (algoxflow + zer0dte) =====
def fetch_cboe_pc_ratio() -> dict:
    """CBOE official P/C ratio CSV — free, no key."""
    result = {"source": "cboe", "timestamp": datetime.now().isoformat()}
    url = "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/indexpcarchive.csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            csv_data = r.read().decode("utf-8", errors="ignore")
        lines = csv_data.strip().split("\n")
        for line in reversed(lines):
            parts = line.split(",")
            if len(parts) >= 5 and parts[0].strip().replace("/", "").isdigit():
                result["date"] = parts[0]
                result["call"] = parts[1]
                result["put"] = parts[2]
                result["total"] = parts[3]
                result["pc_ratio"] = parts[4]
                break
    except Exception as e:
        result["_error"] = str(e)
    return result

# ===== 7. FARSIDE ETF FLOWS =====
def fetch_farside_etf_flows() -> dict:
    """Farside — BTC ETF daily flows (fixed parsing)."""
    result = {"source": "farside", "timestamp": datetime.now().isoformat()}
    html = fetch_html("https://farside.co.uk/btc/", timeout=15)
    if html.startswith("ERROR"):
        result["_error"] = html
        return result
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td', row, re.DOTALL)
        if cells and len(cells) >= 2:
            clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            total = clean[-1]
            date = clean[0]
            result["date"] = date
            result["total_flow"] = total
            break
    return result

# ===== MAIN: CONSOLIDATED FEED =====
def run_data_hub(fred_key: str = None) -> dict:
    print("=" * 60)
    print("ZEUS DATA HUB v2 — Consolidated Market Intelligence")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()

    feed = {"timestamp": datetime.now().isoformat()}

    # 1. FRED Macro
    print("1. FRED MACRO RATES")
    print("-" * 40)
    feed["fred_macro"] = fetch_fred_macro(fred_key)
    if fred_key:
        for k, v in feed["fred_macro"].items():
            if isinstance(v, dict) and "value" in v:
                print(f"   {k}: {v['value']} ({v['date']})")
    else:
        print("   FRED key needed — add fred_key.py with FRED_KEY")
    print()

    # 2. CoinGecko Bulk
    print("2. CRYPTO SWEEP (CoinGecko)")
    print("-" * 40)
    feed["crypto"] = fetch_coingecko_bulk()
    for sym, d in sorted(feed["crypto"]["coins"].items()):
        chg = d.get("change_24h") or 0
        vol = d.get("volume_24h") or 0
        print(f"   {sym}: ${d['price']:.2f} ({chg:+.2f}%) vol={vol:.0f}")
    print()

    # 3. Yahoo Futures
    print("3. FUTURES (Yahoo)")
    print("-" * 40)
    feed["futures"] = fetch_yahoo_futures()
    for f in feed["futures"]:
        chg = f.get("change_24h") or 0
        print(f"   {f['name']}: {f['price']:.2f} ({chg:+.2f}%)")
    print()

    # 4. Forex (Yahoo)
    print("4. FOREX (Yahoo)")
    print("-" * 40)
    feed["forex"] = fetch_forex_yahoo()
    for fx in feed["forex"]:
        if "price" in fx:
            chg = fx.get("change_24h") or 0
            print(f"   {fx['name']}: {fx['price']:.4f} ({chg:+.2f}%)")
    print()

    # 5. International Equities
    print("5. INTERNATIONAL EQUITIES")
    print("-" * 40)
    feed["intl_equities"] = fetch_international_equities()
    for e in feed["intl_equities"]:
        print(f"   {e['name']}: {e['price']:.2f} ({e['change_24h']:+.2f}%)")
    print()

    # 6. Options Gamma (CBOE P/C ratio — free CSV)
    print("6. OPTIONS GAMMA (CBOE P/C)")
    print("-" * 40)
    feed["options_pc"] = fetch_cboe_pc_ratio()
    if "pc_ratio" in feed["options_pc"]:
        print(f"   SPX P/C: {feed['options_pc']['pc_ratio']} ({feed['options_pc']['date']})")
    else:
        print(f"   {feed['options_pc'].get('_error', 'No CBOE data')}")
    print()

    # 7. Farside ETF Flows
    print("7. FARSIDE ETF FLOWS")
    print("-" * 40)
    feed["etf_flows"] = fetch_farside_etf_flows()
    if "total_flow" in feed["etf_flows"]:
        print(f"   BTC ETF flow: {feed['etf_flows']['total_flow']}M ({feed['etf_flows'].get('date', 'N/A')})")
    else:
        print(f"   {feed['etf_flows'].get('_error', 'No flow data')}")
    print()

    # Save
    with open(CACHE_FILE, "w") as f:
        json.dump(feed, f, indent=2)
    print(f"Feed saved to: {CACHE_FILE}")
    print("=" * 60)
    return feed

if __name__ == "__main__":
    try:
        import fred_key
        fred_k = getattr(fred_key, "FRED_KEY", None)
    except ImportError:
        fred_k = None
    run_data_hub(fred_k)
