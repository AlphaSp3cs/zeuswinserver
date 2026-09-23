"""Forex Sentiment Module — COT-based (Myfxbook alternative).
Uses CFTC Commitments of Traders positioning as forex community sentiment.
Signals: CROWDED LONG = fade risk, CROWDED SHORT = squeeze fuel,
FUNDS ADDING = confirm trend, FUNDS COVERING = reversal signal.
"""
import json
from pathlib import Path

COT_FILE = Path("C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/workflow/cot_latest.json")

# Map our symbols to COT data keys
SYM_TO_COT = {
    "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD", "USDCAD": "USDCAD", "USDCHF": "USDCHF",
    "NZDUSD": "NZDUSD", "EURJPY": "EURJPY", "GBPJPY": "GBPJPY",
    "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD", "XTIUSD": "XTIUSD",
    "US500": "US500", "USTEC": "USTEC", "BTCUSD": "BTCUSD",
}

def load_cot():
    try:
        data = json.loads(COT_FILE.read_text())
        return data.get("markets", {})
    except Exception:
        return {}

def get_forex_sentiment(symbol):
    """Get COT-based forex sentiment for a symbol.
    Returns: {signal, net_pct_of_oi, direction, confidence} or None."""
    cot_key = SYM_TO_COT.get(symbol)
    if not cot_key:
        return None
    cot = load_cot().get(cot_key)
    if not cot:
        return None

    signal = cot.get("signal", "")
    net_pct = cot.get("net_pct_of_oi", 0)
    weekly = cot.get("weekly_change", 0)

    # Map COT signal to sentiment direction
    if "CROWDED LONG" in signal:
        direction = "FADE_LONG"  # crowded longs = fade risk
        confidence = min(1.0, abs(net_pct) / 50)
    elif "CROWDED SHORT" in signal:
        direction = "SQUEEZE"  # crowded shorts = squeeze fuel
        confidence = min(1.0, abs(net_pct) / 50)
    elif "ADDING LONGS" in signal and "COVERING" not in signal:
        direction = "BULLISH"
        confidence = 0.7 if net_pct > 10 else 0.4
    elif "ADDING SHORTS" in signal:
        direction = "BEARISH"
        confidence = 0.7 if net_pct < -10 else 0.4
    elif "COVERING" in signal:
        direction = "REVERSAL"  # funds covering = trend reversal
        confidence = 0.6
    else:
        direction = "NEUTRAL"
        confidence = 0.2

    return {
        "symbol": symbol,
        "cot_signal": signal,
        "net_pct_of_oi": net_pct,
        "weekly_change": weekly,
        "direction": direction,
        "confidence": round(confidence, 2),
    }

def scan_all():
    """Scan all forex/crypto pairs for COT sentiment."""
    results = {}
    for sym in SYM_TO_COT:
        r = get_forex_sentiment(sym)
        if r:
            results[sym] = r
    return results

if __name__ == "__main__":
    print("COT Forex Sentiment Scan")
    print("=" * 60)
    data = scan_all()
    for sym, d in sorted(data.items(), key=lambda x: x[1].get("confidence", 0), reverse=True):
        print(f"{sym:10s} {d['direction']:15s} conf={d['confidence']:.0%}  {d['cot_signal']}")
    print(f"\nTotal: {len(data)} pairs")