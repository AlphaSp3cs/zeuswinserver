import os,MetaTrader5 as mt5
log=int(os.getenv('MT5_LOGIN'))
pas=os.getenv('MT5_PASSWORD')
srv=os.getenv('MT5_SERVER')
print('env login',log,'server',srv)
ok=mt5.initialize(login=log,server=srv,password=pas)
print('init',ok,mt5.last_error())
if ok:
    acc=mt5.account_info()
    print('acct',getattr(acc,'login',None),getattr(acc,'server',None),getattr(acc,'equity',None))
    mt5.shutdown()
