import urllib.request, json, base64, hashlib, hmac, time

api_key='3x4rBeKnYKRX6LkCCzm8DYJBZ3de7yw5HWMBSSUwcaxDLVgDl70FSWFW'
api_secret=base64.b64decode('eTjY8NNiNcd8uhsLvcxziyTM8WYMuw13xB981h3ARK9WTHrtkgYXIm7laiwe28uUtfngNqu8xPTVR6hykIlBtw==')

nonce=str(int(time.time()*1000))
url='https://api.kraken.com/0/private/Balance'
post_data='nonce='+nonce
path='/0/private/Balance'

def kraken_sign(path, data, secret):
    post_data=data.encode()
    msg = path.split('.')[0].encode() + hashlib.sha256(str(int(time.time()*1000)).encode() + post_data).digest()
    return base64.b64encode(hmac.new(secret, msg, hashlib.sha512).digest()).decode()

headers={
    'API-Key': api_key,
    'API-Sign': kraken_sign(path, post_data, api_secret),
    'Content-Type': 'application/x-www-form-urlencoded'
}

req=urllib.request.Request(url, data=post_data.encode(), headers=headers, method='POST')
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print('status:', resp.status)
        print(resp.read().decode()[:1000])
except Exception as e:
    print('Error:', e)
