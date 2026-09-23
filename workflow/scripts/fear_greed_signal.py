"""Crypto Fear & Greed Index — OuroTaurus social sentiment overlay.
Alternative.me free API (no key). Replaces LunarCrush which is DNS-blocked.
"""
import requests

API = "https://api.alternative.me/fng/"

def fetch_fear_greed():
    """Fetch current Fear & Greed index. Returns dict or None."""
    try:
        r = requests.get(API, params={"limit": 10}, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        values = data.get("data", [])
        if not values:
            return None
        latest = values[0]
        return {
            "value": int(latest.get("value", 0)),
            "classification": latest.get("value_classification", "unknown"),
            "timestamp": latest.get("timestamp", ""),
            "history": [{"value": int(v["value"]), "label": v["value_classification"], "ts": v["timestamp"]} for v in values],
        }
    except Exception:
        return None

def sentiment_bonus(fg):
    """Convert Fear & Greed to conviction bonus."""
    val = fg.get("value", 50) if fg else 50
    if val <= 20:
        return "BUY", 1.0, "extreme_fear"
    elif val >= 80:
        return "SELL", 1.0, "extreme_greed"
    elif val <= 35:
        return "BUY", 0.5, "fear"
    elif val >= 65:
        return "SELL", 0.5, "greed"
    else:
        return "NEUTRAL", 0, "neutral"

if __name__ == "__main__":
    fg = fetch_fear_greed()
    if fg:
        print(f"Fear & Greed: {fg['value']} — {fg['classification']}")
        side, bonus, tag = sentiment_bonus(fg)
        print(f"Signal: {side} (bonus: {bonus}) tag: {tag}")
        print(f"History: {[(h['value'], h['label']) for h in fg['history'][:5]]}")
    else:
        print("Failed to fetch")