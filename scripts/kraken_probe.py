import os, sys, time, requests
# Try both key files
env_files = [
    r'C:\Users\bravo-usr1\.hermes\ouroboros_backup\.env',
    r'C:\Users\bravo-usr1\.hermes\secure\.env',
]
api_key = secret = None
for ef in env_files:
    if os.path.exists(ef):
        with open(ef,'r') as f:
            for line in f:
                if line.startswith('KRAKEN_API_KEY='):
                    api_key = line.strip().split('=',1)[1].strip().strip('"\'')
                if line.startswith('KRAKEN_API_SECRET='):
                    secret = line.strip().split('=',1)[1].strip().strip('"\'')
        if api_key and secret:
            break

if not api_key or not secret:
    print('No Kraken keys found')
    sys.exit(1)

nonce = str(int(time.time() * 1000000))
path = '/0/private/Balance'
data = {'nonce': nonce, 'apikey': api_key}
msg = (data['nonce'] + data['apikey'] + path + str(data)).encode()
import base64, hashlib, hmac
secret_decoded = base64.b64decode(secret)
signature = base64.b64encode(hmac.new(secret_decoded, msg, hashlib.sha512).digest()).decode()
headers = {'API-Key': api_key, 'API-Sign': signature}
resp = requests.post('https://api.kraken.com' + path, headers=headers, json=data, timeout=15)
print('Status:', resp.status_code)
print('Response:', resp.text[:500])
