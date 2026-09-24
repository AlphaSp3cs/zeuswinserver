import sys, os, time, json
sys.path.insert(0, 'C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
os.chdir('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
from pathlib import Path
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order

# Load .env
env_path = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/.env')
for line in env_path.read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line:
        continue
    k, v = line.split('=', 1)
    os.environ[k.strip()] = v.strip().strip('"').strip("'")


class S(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.nid = None

    def nextValidId(self, i):
        self.nid = i


app = S()
app.connect(
    os.environ.get('IBKR_HOST', '127.0.0.1'),
    int(os.environ.get('IBKR_PORT', '7497')),
    int(os.environ.get('IBKR_CLIENT_ID', '1')) + 200,
)

for _ in range(30):
    app.run()
    if app.nid is not None:
        break
    time.sleep(0.1)

if app.nid is None:
    print('NO_NEXT_VALID_ID')
    sys.exit(1)

orders = [
    (
        'SPY covered call',
        Contract(symbol='SPY', secType='OPT', exchange='SMART', currency='USD',
                 lastTradeDateOrContractMonth='202608', right='C', strike=740, multiplier='100'),
        Order(action='SELL', orderType='LMT', totalQuantity=2, lmtPrice=8.5, tif='GTC'),
    ),
    (
        'QQQ covered call',
        Contract(symbol='QQQ', secType='OPT', exchange='SMART', currency='USD',
                 lastTradeDateOrContractMonth='202608', right='C', strike=690, multiplier='100'),
        Order(action='SELL', orderType='LMT', totalQuantity=1, lmtPrice=7.0, tif='GTC'),
    ),
    (
        'TSLA protective put',
        Contract(symbol='TSLA', secType='OPT', exchange='SMART', currency='USD',
                 lastTradeDateOrContractMonth='202608', right='P', strike=300, multiplier='100'),
        Order(action='BUY', orderType='LMT', totalQuantity=15, lmtPrice=12.0, tif='GTC'),
    ),
    (
        'AMD call hedge',
        Contract(symbol='AMD', secType='OPT', exchange='SMART', currency='USD',
                 lastTradeDateOrContractMonth='202608', right='C', strike=540, multiplier='100'),
        Order(action='BUY', orderType='LMT', totalQuantity=12, lmtPrice=5.0, tif='GTC'),
    ),
    (
        'SPY put hedge',
        Contract(symbol='SPY', secType='OPT', exchange='SMART', currency='USD',
                 lastTradeDateOrContractMonth='202608', right='P', strike=720, multiplier='100'),
        Order(action='BUY', orderType='LMT', totalQuantity=2, lmtPrice=3.5, tif='GTC'),
    ),
]

results = []
for i, (name, c, o) in enumerate(orders, 1):
    oid = app.nid + i - 1
    app.placeOrder(oid, c, o)
    results.append({
        'order_id': oid,
        'name': name,
        'symbol': c.symbol,
        'action': o.action,
        'qty': o.totalQuantity,
        'price': getattr(o, 'lmtPrice', None),
    })
    time.sleep(0.2)

out = {
    'timestamp': __import__('datetime').datetime.now().isoformat(),
    'orders': results,
    'submitted': len(results),
}
Path('ibkr_submit_results_2026-07-26.json').write_text(json.dumps(out, indent=2))
print('SUBMITTED', len(results), 'orders')
for r in results:
    print(r)

try:
    app.disconnect()
except Exception:
    pass
