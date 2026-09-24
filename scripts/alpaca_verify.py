
import requests, json
BASE = 'https://paper-api.alpaca.markets'
HEADERS = {
    'APCA-API-KEY-ID': 'PKQXYUCBUOU5OEGLJPREBAZFKM',
    'APCA-API-SECRET-KEY': 'CNUwyrSYQsjzbP45E5qPB3SDxkfUAb1ZgHQBEfgigRB3'
}
out = {}
try:
    r = requests.get(f"{BASE}/v2/account", headers=HEADERS, timeout=20)
    out['account_status'] = r.status_code
    out['account'] = r.json() if r.status_code == 200 else r.text[:300]
except Exception as e:
    out['account_exception'] = repr(e)
try:
    r = requests.get(f"{BASE}/v2/positions", headers=HEADERS, timeout=20)
    out['positions_status'] = r.status_code
    out['positions'] = r.json() if r.status_code == 200 else r.text[:300]
except Exception as e:
    out['positions_exception'] = repr(e)
print(json.dumps(out, indent=2))
