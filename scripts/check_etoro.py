import json, os, requests, uuid
from pathlib import Path

BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
ETORO_BASE_URL = 'https://public-api.etoro.com/api/v1'

def _load_etoro_creds():
    path = BASE_FIRM / '.broker_creds_secure.json'
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            etoro = data.get('etoro') or data.get('ETORO') or {}
            if etoro.get('api_key') and etoro.get('user_key'):
                return etoro['api_key'], etoro['user_key']
        except Exception:
            pass
    api_key = os.environ.get('ETORO_API_KEY')
    user_key = os.environ.get('ETORO_USER_KEY')
    if api_key and user_key:
        return api_key, user_key
    raise SystemExit('Missing eToro credentials in .broker_creds_secure.json and ETORO_API_KEY/ETORO_USER_KEY env')

ETORO_API_KEY, ETORO_USER_KEY = _load_etoro_creds()

headers = {
    'x-request-id': str(uuid.uuid4()),
    'x-api-key': ETORO_API_KEY,
    'x-user-key': ETORO_USER_KEY,
    'Accept': 'application/json',
}

for account_type in ['demo', 'real']:
    resp = requests.get(f'{ETORO_BASE_URL}/trading/info/{account_type}/pnl', headers=headers, timeout=10)
    print(f'eToro {account_type}: {resp.status_code}')
    if resp.status_code == 200:
        data = resp.json()
        positions = data.get('clientPortfolio', {}).get('positions', [])
        for pos in positions:
            if pos.get('mirrorID', 0) == 0:  # Skip copy trades
                entry = pos.get('openRate', 0)
                current = pos.get('currentRate', 0)
                direction = pos.get('direction', 'BUY')
                units = pos.get('units', 0)
                instrument_id = pos.get('instrumentID', 0)
                position_id = pos.get('positionID', 0)
                pl = pos.get('pl', 0)
                if entry > 0:
                    if direction == 'BUY':
                        pnl_pct = ((current - entry) / entry) * 100
                    else:
                        pnl_pct = ((entry - current) / entry) * 100
                else:
                    pnl_pct = 0
                print(f'  {pos.get("instrumentDisplayName", "")} {direction} Units:{units} Entry:{entry:.5f} Curr:{current:.5f} PnL%:{pnl_pct:.2f} SL:{pos.get("stopLossRate", 0)} TP:{pos.get("takeProfitRate", 0)} PL:\${pl:.2f}')
    else:
        print(f'  Error: {resp.text[:200]}')