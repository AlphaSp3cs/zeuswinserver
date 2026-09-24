import MetaTrader5 as mt5, json, time
from pathlib import Path
from datetime import datetime

CAP_PATH='C:/Program Files/Capital.com MetaTrader 5/terminal64.exe'
LOGIN = int(os.environ.get('CAPITAL_MT5_LOGIN', '0'))
PW=os.environ.get('CAPITAL_MT5_PASSWORD', '')
SERVER=os.environ.get('CAPITAL_MT5_SERVER', 'Capital.ComBah-Demo')

def line(t,s=''):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {t} {s}", flush=True)

line('=== CAPITAL.COM MT5 (RIGHT) DRIVER DIAGNOSTIC ===')
mt5.shutdown()
ok=mt5.initialize(CAP_PATH, login=LOGIN, password=PW, server=SERVER)
line('init', 'OK' if ok else f'FAIL {mt5.last_error()}')
if not ok:
    ok=mt5.initialize(CAP_PATH, login=LOGIN, password=PW)
    line('init (no server)', 'OK' if ok else f'FAIL {mt5.last_error()}')
    if not ok:
        print(json.dumps({'verdict':'BROKEN','reason':'cannot init with stored creds'},indent=2)); mt5.shutdown(); raise SystemExit

acct=mt5.account_info()
line('account', f"login={acct.login} server={acct.server} equity={round(acct.equity,2)} free={round(acct.margin_free,2)} trade_allowed={getattr(acct,'trade_allowed',None)} mode={getattr(acct,'trade_mode',None)}")

for sym in ['BTCUSD','ETHUSD','XRPUSD','EURUSD']:
    si=mt5.symbol_info(sym)
    if si is None:
        line('symbol', f'{sym} NOT FOUND'); continue
    if not si.visible: mt5.symbol_select(sym,True)
    tick=mt5.symbol_info_tick(sym)
    line('symbol', f'{sym} bid={tick.bid if tick else None} ask={tick.ask if tick else None} stops={si.trade_stops_level} vis={si.visible}')

vi=mt5.version()
line('mt5 version', vi)
term=mt5.terminal_info()
line('terminal', f"connected={getattr(term,'connected',None)}")

sym='XRPUSD'
si=mt5.symbol_info(sym); mt5.symbol_select(sym,True); tick=mt5.symbol_info_tick(sym)
dig=si.digits; pt=10**(-dig)
price=tick.ask
sl=round(price*(1-0.025),dig); tp=round(price*(1+0.05),dig)
buf=si.trade_stops_level+15
if int((tick.bid-sl)/pt)<buf: sl=round(tick.bid-buf*pt,dig)
vol=0.01
req={'action':mt5.TRADE_ACTION_DEAL,'symbol':sym,'volume':float(vol),'type':mt5.ORDER_TYPE_BUY,
     'price':float(price),'deviation':50,'sl':float(sl),'tp':float(tp),'comment':'DRVTEST','magic':20260728}
res=mt5.order_send(req)
line('TEST ORDER', f"retcode={res.retcode} order={res.order} fill={res.price}")
ok_fill = res.retcode==mt5.TRADE_RETCODE_DONE
time.sleep(1)
pos=mt5.positions_get(symbol=sym)
ok_close=False
if pos:
    p=pos[0]
    close={'action':mt5.TRADE_ACTION_DEAL,'symbol':sym,'volume':p.volume,
           'type':mt5.ORDER_TYPE_SELL if p.type==0 else mt5.ORDER_TYPE_BUY,
           'deviation':50,'comment':'DRVTEST_CLOSE','magic':20260728}
    cres=mt5.order_send(close)
    line('TEST CLOSE', f"retcode={cres.retcode} fill={cres.price}")
    ok_close = cres.retcode==mt5.TRADE_RETCODE_DONE
else:
    line('TEST CLOSE', 'no position')

mt5.shutdown()
verdict='GOOD' if (ok and ok_fill and ok_close) else ('PARTIAL' if ok else 'BROKEN')
out={'verdict':verdict,'init':ok,'test_order_fill':ok_fill,'test_close':ok_close,
     'equity':round(acct.equity,2),'login':LOGIN,'server':SERVER}
Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/capital_driver_diag_20260728.json').write_text(json.dumps(out,indent=2))
line('VERDICT', verdict)
print(json.dumps(out,indent=2))
