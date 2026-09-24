#!/usr/bin/env python3
"""Broker verification workflow for Pack profiles."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_broker_creds import get, health_check

BASE = Path(__file__).resolve().parent.parent
RESULTS_PATH = BASE / 'scandata' / 'broker_verification_results.json'


def verify_broker(name: str) -> dict:
    """Run read-only verification for a broker if possible."""
    broker = get(name)
    result = health_check(name)
    result['verified'] = False
    result['verification_error'] = None

    if name.lower() == 'capital':
        try:
            import MetaTrader5 as mt5
            if mt5.initialize(
                login=int(broker.get('login', 0)),
                password=broker.get('password', ''),
                server=broker.get('server', ''),
                path=broker.get('terminal', ''),
            ):
                acc = mt5.account_info()
                if acc:
                    result['verified'] = True
                    result['account_summary'] = {
                        'login': acc.login,
                        'balance': acc.balance,
                        'equity': acc.equity,
                        'trade_mode': acc.trade_mode,
                    }
                else:
                    result['verification_error'] = 'account_info returned None'
                mt5.shutdown()
            else:
                result['verification_error'] = str(mt5.last_error())
        except Exception as e:
            result['verification_error'] = str(e)

    elif name.lower() == 'alpaca':
        try:
            import requests
            headers = {
                'APCA-API-KEY-ID': broker.get('api_key', ''),
                'APCA-API-SECRET-KEY': broker.get('secret_key', ''),
            }
            base = broker.get('base_url', 'https://paper-api.alpaca.markets/v2').rstrip('/')
            url = f"{base}/v2/account" if not base.endswith('/v2') else f"{base}/account"
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                result['verified'] = True
                try:
                    result['account_summary'] = r.json()
                except Exception:
                    result['account_summary'] = r.text[:200]
            else:
                result['verification_error'] = f"{r.status_code}: {r.text[:200]}"
        except Exception as e:
            result['verification_error'] = str(e)

    elif name.lower() == 'etoro':
        try:
            import requests, uuid
            headers = {
                'x-api-key': broker.get('api_key', ''),
                'x-user-key': broker.get('private_key', ''),
                'x-request-id': str(uuid.uuid4()),
            }
            base = broker.get('base_url', 'https://public-api.etoro.com')
            r = requests.get(f"{base}/api/v1/me", headers=headers, timeout=15)
            if r.status_code == 200:
                result['verified'] = True
                result['account_summary'] = r.text[:200]
            else:
                result['verification_error'] = f"{r.status_code}: {r.text[:200]}"
        except Exception as e:
            result['verification_error'] = str(e)

    elif name.lower() == 'ibkr':
        try:
            from ibapi.client import EClient
            from ibapi.wrapper import EWrapper
            import threading, time

            class IBProbe(EWrapper, EClient):
                def __init__(self):
                    EClient.__init__(self, self)
                    self.connected = False
                    self.accounts = []
                    self.account_data = []
                    self.account_download_done = threading.Event()
                    self.errors = []
                def connectAck(self):
                    self.connected = True
                def nextValidId(self, orderId):
                    if broker.get('account'):
                        self.reqAccountUpdates(True, broker['account'])
                def managedAccts(self, accountsList):
                    self.accounts = [a.strip() for a in accountsList.split(',') if a.strip()]
                def updateAccountValue(self, key, value, currency, accountName):
                    self.account_data.append({
                        'key': key,
                        'value': value,
                        'currency': currency,
                        'account': accountName,
                    })
                def accountDownloadEnd(self, accountName):
                    self.account_download_done.set()
                def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=None):
                    # Ignore market-data/connectivity info messages
                    if errorCode not in {2104, 2106, 2158, 2159, 2168, 2169}:
                        self.errors.append({'reqId': reqId, 'code': errorCode, 'msg': errorString})

            ib = IBProbe()
            ib.connect(
                broker.get('host', '127.0.0.1'),
                int(broker.get('port', 4002)),
                clientId=int(broker.get('client_id', '2002')),
            )
            t = threading.Thread(target=ib.run, daemon=True)
            t.start()
            time.sleep(5)
            account_done = ib.account_download_done.wait(timeout=10)
            if account_done or ib.connected or len(ib.account_data) > 0:
                result['verified'] = True
                result['account_summary'] = {
                    'managed_accounts': ib.accounts,
                    'account_data_count': len(ib.account_data),
                    'sample_account_data': ib.account_data[:5],
                    'errors': ib.errors,
                    'verification_detail': {
                        'account_download_done': account_done,
                        'connected': ib.connected,
                    }
                }
            else:
                result['verification_error'] = 'connectAck not received or account download timed out'
            ib.disconnect()
        except Exception as e:
            result['verification_error'] = str(e)

    elif name.lower() == 'kraken':
        try:
            import requests
            r = requests.get(f"{broker.get('base_url', 'https://api.kraken.com')}/0/public/Time", timeout=15)
            if r.status_code == 200:
                result['verified'] = True
                result['account_summary'] = {'public_time': r.json()}
            else:
                result['verification_error'] = f"{r.status_code}: {r.text[:200]}"
        except Exception as e:
            result['verification_error'] = str(e)

    return result


def run_verification():
    names = ['capital', 'alpaca', 'etoro', 'ibkr', 'kraken']
    results = {}
    blocked = []
    for name in names:
        results[name] = verify_broker(name)
        if not results[name].get('verified'):
            blocked.append(name)
    output = {
        'timestamp': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'results': results,
        'blocked': sorted(set(blocked)),
        'allow_trading': len(blocked) == 0,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(output, indent=2), encoding='utf-8')
    return output


if __name__ == '__main__':
    output = run_verification()
    print(json.dumps(output, indent=2))
    if output['blocked']:
        raise SystemExit(2)
