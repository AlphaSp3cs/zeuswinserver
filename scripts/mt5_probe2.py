import os,MetaTrader5 as mt5
log=os.getenv('MT5_LOGIN')
pas=os.getenv('MT5_PASSWORD')
srv=os.getenv('MT5_SERVER')
p=r'REDACTED-PATH'
ok=mt5.initialize(path=p,login=int(log),server=srv,password=pas)
print('init',ok,mt5.last_error())
acc=mt5.account_info() if ok else None
print('acct',getattr(acc,'login',None),getattr(acc,'server',None),getattr(acc,'equity',None))
mt5.shutdown()