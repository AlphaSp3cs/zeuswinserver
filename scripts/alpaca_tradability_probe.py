import requests, os, json
base='https://paper-api.alpaca.markets'
key=os.getenv('APCA_API_KEY_ID') or os.getenv('ALPACA_API_KEY_ID')
secret=os.getenv('APCA_API_SECRET_KEY') or os.getenv('ALPACA_API_SECRET_KEY')
headers={'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}
sym=['NEE','SPGI','O','MCO','AXP','PEP','WMT','IBM','LIN','TXN','PG','DHR','JNJ','CL','DE','CVX','KO','XOM','CME','TMO','JPM','SHW','ROP','ABT','MCD','V','MA','ITW','EMR','MMM']
out={}
for s in sym:
    try:
        r=requests.get(f"{base}/v2/assets/{s}", headers=headers, timeout=10)
        d=r.json() if r.status_code==200 else {}
        out[s]={'status':r.status_code,'symbol':d.get('symbol'),'tradable':d.get('tradable'),'status_asset':d.get('status')}
    except Exception as e:
        out[s]={'status':'ERROR','error':str(e)}
print(json.dumps(out, indent=2))
