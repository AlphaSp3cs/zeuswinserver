import MetaTrader5 as mt5, json

CRED = {
    "path": r"C:\Program Files\Capital.com MetaTrader 5\terminal64.exe",
    "login": int(os.environ.get('CAPITAL_MT5_LOGIN', '1028685')),
    "password": os.environ.get('CAPITAL_MT5_PASSWORD', ''),
    "server": os.environ.get('CAPITAL_MT5_SERVER', 'Capital.ComBah-Demo'),
}

print("Initializing Capital.com MT5 (RIGHT)...")
ok = mt5.initialize(**CRED)
if not ok:
    print("INIT FAILED:", mt5.last_error())
    raise SystemExit(1)

acc = mt5.account_info()
print(f"CONNECTED -> login={acc.login} balance={acc.balance} equity={acc.equity} "
      f"server={acc.server} currency={acc.currency}")
print("trade_mode:", acc.trade_mode, "(0=real,1=demo,3=disable,4=closeonly)")

targets = ["ZEC","ETH","XRP","BTC","SOL","AVAX","AAVE","XMR","DOGE","WLD","NEAR"]
all_syms = mt5.symbols_get()
print("total symbols on broker:", len(all_syms))
found = {}
for t in targets:
    matches = [s.name for s in all_syms if t.upper() in s.name.upper()]
    found[t] = matches[:8]
print("TARGET MATCHES:")
for t, m in found.items():
    print(f"  {t}: {m}")

# also report existing positions
pos = mt5.positions_get() or []
print("OPEN POSITIONS:", len(pos))
for p in pos:
    print(f"  ticket={p.ticket} sym={p.symbol} type={p.type} vol={p.volume} sl={p.sl} tp={p.tp}")

mt5.shutdown()
