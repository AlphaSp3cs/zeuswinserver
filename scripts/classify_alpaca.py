"""B) LIVE ALPACA BOOK CLASSIFIER — same winning/losing logic as the backtest,
applied to the REAL open positions on Alpaca PAPER. For each holding we:
  - pull live position (qty, avg_entry, uPNL)
  - pull entry date from the actual filled buy order
  - load 1y daily history (Yahoo) and compute SMA50 + RSI at entry and now
  - classify WIN/LOSS + entry-regime (falling-knife?) + current-regime + RSI
Read-only. No orders."""
import urllib.request, base64, json, csv, os
from datetime import datetime

OUT='C:/Users/bravo-usr1/trade_data'
key="PKXJMRKXOJILYBZ6TMFAKHQDZY"; secret="7KQioWBVjuwTRAGZCBm3xBVFsn4wBQZr6cwUrSXME2WE"
auth=base64.b64encode(f"{key}:{secret}".encode()).decode()
H={"Authorization":f"Basic {auth}"}
def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30))

def closes_of(fpath):
    rows=list(csv.DictReader(open(fpath)))
    return {r['date']: float(r['close']) for r in rows}, [float(r['close']) for r in rows]

def sma_at(closes_list, i, n=50):
    if i+1<n: return None
    return sum(closes_list[i+1-n:i+1])/n
def rsi_series(closes, n=14):
    out=[None]*len(closes); g=[]; l=[]
    for i in range(1,len(closes)):
        ch=closes[i]-closes[i-1]; g.append(max(ch,0)); l.append(max(-ch,0))
    if len(g)<n: return out
    ag=sum(g[:n])/n; al=sum(l[:n])/n
    out[n]=100-(100/(1+(ag/al) if al>0 else 999))
    for i in range(n+1,len(closes)):
        ag=(ag*(n-1)+g[i-1])/n; al=(al*(n-1)+l[i-1])/n
        out[i]=100-(100/(1+(ag/al if al>0 else 999)))
    return out

# live positions
pos=get("https://paper-api.alpaca.markets/v2/positions")
# entry dates from filled buy orders
orders=get("https://paper-api.alpaca.markets/v2/orders?status=closed&limit=500")
entry_date={}
for o in orders:
    if o.get('side')=='buy' and o.get('filled_at') and o.get('symbol') not in entry_date:
        entry_date[o['symbol']]=o['filled_at'][:10]

print("="*86)
print("B) LIVE ALPACA PAPER BOOK — WIN/LOSS CLASSIFICATION (real positions, Yahoo 1y history)")
print("="*86)
print(f"{'SYM':8}{'uPNL$':>9}{'WIN?':>6}{'ENTRY':>11}{'ENTRY-REGIME':>16}{'NOW-RSI':>8}{'NOW-REGIME':>14}")
print("-"*86)
losers=[]
for p in pos:
    sym=p['symbol']; upnl=float(p.get('unrealized_pl') or 0)
    win = upnl>=0
    fname=f'{OUT}/yh_{sym}.csv'
    if not os.path.exists(fname):
        print(f"{sym:8}{upnl:>9.2f}{('WIN' if win else 'LOSS'):>6}  (no history file)"); 
        if not win: losers.append(sym)
        continue
    dmap,closes=closes_of(fname)
    dates=list(dmap.keys())
    R=rsi_series(closes)
    # entry regime
    ed=entry_date.get(sym, dates[0])
    ei=max(0, next((i for i,d in enumerate(dates) if d>=ed), len(dates)-1))
    s50e=sma_at(closes, ei)
    entry_regime = 'UPTREND' if (s50e and closes[ei]>s50e) else ('DOWNTREND' if s50e else '?')
    # now
    ni=len(closes)-1
    s50n=sma_at(closes, ni)
    now_regime = 'ABOVE SMA50' if (s50n and closes[ni]>s50n) else ('BELOW SMA50' if s50n else '?')
    rsi_now = R[ni] if R[ni] else 0
    tag = 'WIN' if win else 'LOSS'
    print(f"{sym:8}{upnl:>9.2f}{tag:>6}  {ed:>11}{entry_regime:>16}{rsi_now:>8.1f}{now_regime:>14}")
    if not win: losers.append(sym)

print("-"*86)
print("LOSING POSITIONS:", losers if losers else "none")
print()
print("INTERPRETATION:")
print("  Compare to MT5: those losers were FALLING-KNIFE (entered below SMA50 in")
print("  a downtrend). Check each Alpaca loser's ENTRY-REGIME above.")
print("  If any Alpaca loser shows 'DOWNTREND' at entry, it's the SAME bug —")
print("  the bot bought oversold without a market-regime gate.")
