import urllib.request, base64, json
key="PKXJMRKXOJILYBZ6TMFAKHQDZY"; secret="7KQioWBVjuwTRAGZCBm3xBVFsn4wBQZr6cwUrSXME2WE"
auth=base64.b64encode(f"{key}:{secret}".encode()).decode()
H={"Authorization":f"Basic {auth}"}
def get(u):
    req=urllib.request.Request(u, headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)
a=get("https://paper-api.alpaca.markets/v2/account")
print("ACCOUNT KEYS:", list(a.keys()))
print("EQUITY", a.get('equity'), "PORTFOLIO_VALUE", a.get('portfolio_value'), "CASH", a.get('cash'), "BP", a.get('buying_power'))
orders=get("https://paper-api.alpaca.markets/v2/orders?status=closed&limit=500")
print("TOTAL CLOSED ORDERS", len(orders))
print("SAMPLE ORDER KEYS:", list(orders[0].keys()))
sells=[o for o in orders if o.get('side')=='sell' and o.get('filled_avg_price')]
print("CLOSED SELLS w/ fill:", len(sells))
pnls={}
for o in sells:
    sym=o['symbol']
    pnl=o.get('realized_pl')
    if pnl is not None:
        pnls.setdefault(sym,0.0); pnls[sym]+=float(pnl)
print("REALIZED PnL by symbol (closed sells):")
for s,v in sorted(pnls.items(), key=lambda x:x[1]):
    print(f"  {s}: {v:+.2f}")
for sym in ['GLD','REMX','UNG','XLY']:
    try:
        bars=get(f"https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Day&limit=180&adjustment=split")
        b=bars.get('bars',[])
        if b:
            print(f"{sym} bars={len(b)} first_close={b[0]['c']} last_close={b[-1]['c']} date0={b[0]['t'][:10]} date1={b[-1]['t'][:10]}")
        else:
            print(sym,"no bars")
    except Exception as e:
        print(sym,"ERR",e)
