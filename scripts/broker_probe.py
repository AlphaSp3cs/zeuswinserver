import urllib.request, urllib.parse, hashlib, hmac, base64, json, time

def kraken():
    # from allapi2026.txt: key='/9JobVRqtZhShvvALwn0nKy76LlHyOBqFLX25sFf0Mr3U3aXBM2c5KBL', secret base64-ish
    api_key="/9JobVRqtZhShvvALwn0nKy76LlHyOBqFLX25sFf0Mr3U3aXBM2c5KBL"
    secret="s5rREfeY1bZnwMv2A249zeqH7nbyr5Kry5gIysci/oyC6EEU0RVbjh+539QRenG01b/vpbGcj85ct4JzzYtVaw=="
    try:
        # decode secret (handle urlsafe)
        s=secret
        s+='='*(-len(s)%4)
        sec=base64.b64decode(s)
        nonce=str(int(time.time()*1000))
        path="/0/private/Balance"
        data=urllib.parse.urlencode({"nonce":nonce})
        sig=hmac.new(sec, (nonce+data).encode(), hashlib.sha512).hexdigest()
        req=urllib.request.Request("https://api.kraken.com"+path, data=data.encode(),
            headers={"API-Key":api_key,"API-Sign":sig})
        with urllib.request.urlopen(req, timeout=20) as r:
            j=json.load(r)
        if j.get('error'): print("KRAKEN error:", j['error']); return
        print("KRAKEN balance:", {k:float(v) for k,v in j['result'].items() if float(v)>0} or "empty")
    except Exception as e:
        print("KRAKEN ERR:", type(e).__name__, str(e)[:200])

def binance():
    key="O59GjgYTJ3y4MjG6yuPI7IFf2o2LquM18Rzx3Xbk7anVIThjaVYzNXIOHExCDif2"
    secret="IjjzMxheCNjOfLcaO0IA1YOxlQ0yrS0xEMHKs5Q7hGYpkBgqFxnUAr2YyIM0RkmX"
    try:
        tp=int(time.time()*1000)
        q=urllib.parse.urlencode({"timestamp":tp})
        sign=hmac.new(secret.encode(), q.encode(), hashlib.sha256).hexdigest()
        url=f"https://api.binance.us/api/v3/account?{q}&signature={sign}"
        req=urllib.request.Request(url, headers={"X-MBX-APIKEY":key})
        with urllib.request.urlopen(req, timeout=20) as r:
            j=json.load(r)
        print("BINANCE balances>0:", len(j.get('balances',[])), "canTrade:", j.get('canTrade'))
        pos={b['asset']:float(b['free'])+float(b['locked']) for b in j['balances'] if float(b['free'])+float(b['locked'])>0}
        print("  ", pos or "none")
    except urllib.error.HTTPError as e:
        print("BINANCE HTTP", e.code, e.read()[:200].decode(errors='ignore'))
    except Exception as e:
        print("BINANCE ERR:", type(e).__name__, str(e)[:200])

kraken(); binance()
