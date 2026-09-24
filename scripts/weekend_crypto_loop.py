#!/usr/bin/env python3
"""
OuroTaurus Weekend Crypto Loop — runs Sat/Sun only.
Crypto trades 24/7 so the challenge engine keeps compounding on weekends.
Same scan/execute logic as daily_growth_loop but crypto-only universe,
and it SKIPS equity/FX. Sizing stays challenge-safe.
"""
import json, time, sys, traceback
from pathlib import Path
from datetime import datetime

ROOT = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
ALLPI = ROOT / 'allapi2026.txt'
PASTE = Path('C:/Users/bravo-usr1/AppData/Local/hermes/pastes/paste_4_072737.txt')
LOGDIR = ROOT / 'logs'
LOGDIR.mkdir(exist_ok=True)

def log(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)

def load_creds():
    creds = {}
    if ALLPI.exists():
        import re
        for line in ALLPI.read_text(errors='ignore').splitlines():
            s = line.strip()
            if s.startswith('#') or not s: continue
            if 'Capital.com' in s:
                p = s.split(); creds['capital'] = {'login': int(p[2]), 'pw': p[3], 'server': p[4]}
            if 'FTMO MT5 login' in s and 'current live' in s:
                m = re.search(r'login\s+(\d+)\s+password\s+(\S+)', s)
                if m: creds['ftmo'] = {'login': int(m.group(1)), 'pw': m.group(2), 'server': os.environ.get('FTMO_MT5_SERVER', '')}
    if PASTE.exists():
        lines = PASTE.read_text(errors='ignore').splitlines()
        for i, line in enumerate(lines):
            ls = line.strip().lower()
            if ls.startswith('public key'):
                creds['etoro_api'] = line.split(':',1)[1].strip() if ':' in line else lines[i+1].strip()
            if ls.startswith('private key'):
                creds['etoro_user'] = line.split(':',1)[1].strip() if ':' in line else lines[i+1].strip()
    return creds

def yf_chart(sym, rng='5d', inter='1h'):
    import requests
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={inter}'
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
    return r.json()['chart']['result'][0]

def rsi(closes, n=14):
    g = [max(0, c2-c1) for c1,c2 in zip(closes, closes[1:])]
    l = [max(0, c1-c2) for c1,c2 in zip(closes, closes[1:])]
    ag = sum(g[-n:])/n; al = sum(l[-n:])/n
    return 100.0 if al == 0 else 100 - 100/(1+ag/al)

def scan_crypto():
    import requests
    universe = ['BTC-USD','ETH-USD','SOL-USD','XRP-USD','ADA-USD','DOGE-USD','DOT-USD','LINK-USD']
    sigs = []
    for s in universe:
        try:
            d = yf_chart(s)
            closes = [c for c in d['indicators']['quote'][0]['close'] if c]
            if len(closes) < 20: continue
            r = rsi(closes[-30:])
            mom = (closes[-1]-closes[-5])/closes[-5]*100
            if r > 52 and r < 74 and mom > 0.3:
                side = 'BUY'
            elif r < 48 and r > 26 and mom < -0.3:
                side = 'SELL'
            else:
                continue
            sigs.append({'mt': s.replace('-USD','USD').upper(), 'yf': s, 'rsi': round(r,1), 'mom': round(mom,2), 'last': closes[-1], 'side': side})
        except: continue
    sigs.sort(key=lambda x: abs(x['mom']), reverse=True)
    return sigs[:8]

def exec_mt5(term_path, cred, signals, vol_map):
    import MetaTrader5 as mt5
    mt5.shutdown()
    if not mt5.initialize(term_path, login=cred['login'], password=cred['pw'], server=cred['server']):
        return {'init': False}
    filled, failed = [], []
    for sig in signals:
        sym = sig['mt']; side = sig['side']
        si = mt5.symbol_info(sym)
        if not si:
            failed.append({'sym': sym, 'reason': 'no_symbol'}); continue
        if not si.visible: mt5.symbol_select(sym, True)
        tick = mt5.symbol_info_tick(sym)
        if not tick: failed.append({'sym': sym, 'reason': 'no_tick'}); continue
        dig = si.digits; pt = 10**(-dig)
        price = tick.ask if side == 'BUY' else tick.bid
        if side == 'BUY':
            sl = round(price*(1-0.025), dig); tp = round(price*(1+0.05), dig)
        else:
            sl = round(price*(1+0.025), dig); tp = round(price*(1-0.05), dig)
        buf = si.trade_stops_level + 15
        if side == 'BUY' and int((tick.bid-sl)/pt) < buf: sl = round(tick.bid-buf*pt, dig)
        if side == 'SELL' and int((sl-tick.bid)/pt) < buf: sl = round(tick.bid+buf*pt, dig)
        vol = vol_map.get(sym, 0.01)
        req = {'action': mt5.TRADE_ACTION_DEAL, 'symbol': sym, 'volume': float(vol),
               'type': mt5.ORDER_TYPE_BUY if side == 'BUY' else mt5.ORDER_TYPE_SELL,
               'price': float(price), 'deviation': 50, 'sl': float(sl), 'tp': float(tp), 'comment': 'wknd', 'magic': 20260728}
        res = mt5.order_send(req)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            filled.append({'sym': sym, 'vol': vol, 'fill': res.price, 'sl': sl, 'tp': tp})
        else:
            failed.append({'sym': sym, 'reason': res.retcode})
        time.sleep(0.5)
    mt5.shutdown()
    return {'init': True, 'filled': filled, 'failed': failed}

def exec_etoro(creds, signals):
    import requests, uuid
    if 'etoro_api' not in creds: return []
    api = creds['etoro_api']; user = creds['etoro_user']
    base = 'https://public-api.etoro.com'
    emap = {'BTCUSD':'BTC','ETHUSD':'ETH','XRPUSD':'XRP','SOLUSD':'SOL','DOGEUSD':'DOGE','LINKUSD':'LINK','ADAUSD':'ADA','DOTUSD':'DOT'}
    out = []
    for sig in signals:
        et = emap.get(sig['mt'])
        if not et: continue
        h = {'x-request-id': str(uuid.uuid4()), 'x-api-key': api, 'x-user-key': user, 'Accept':'application/json','Content-Type':'application/json'}
        order = {'action':'open','transaction':'buy','symbol':et,'orderType':'mkt','leverage':1,'amount':40.0,'orderCurrency':'usd'}
        try:
            r = requests.post(f'{base}/api/v2/trading/execution/demo/orders', headers=h, json=order, timeout=30)
            out.append({'et': et, 'status': r.status_code})
        except Exception as e:
            out.append({'et': et, 'err': str(e)[:60]})
        time.sleep(0.5)
    return out

def main():
    run_ts = datetime.now().strftime('%Y-%m-%d_%H%M')
    log(f"=== Weekend crypto loop {run_ts} ===")
    creds = load_creds()
    signals = scan_crypto()
    log(f"crypto signals: {len(signals)} -> {[(s['mt'],s['side'],s['rsi'],s['mom']) for s in signals]}")
    if not signals:
        log("no crypto signals; standing down.")
        return {'signals': 0}
    ftmo_vol = {'ETHUSD':0.02,'SOLUSD':0.02,'DOGEUSD':0.05,'LINKUSD':0.02,'BTCUSD':0.02,'XRPUSD':0.05,'ADAUSD':0.02,'DOTUSD':0.02}
    cap_vol  = {'ETHUSD':0.01,'SOLUSD':0.01,'DOGEUSD':0.02,'LINKUSD':0.01,'BTCUSD':0.01,'XRPUSD':0.01,'ADAUSD':0.01,'DOTUSD':0.01}
    r_ftmo = exec_mt5('C:/Program Files/FTMO Global Markets MT5 Terminal/terminal64.exe', creds['ftmo'], signals, ftmo_vol) if 'ftmo' in creds else {}
    r_cap  = exec_mt5('C:/Program Files/Capital.com MetaTrader 5/terminal64.exe', creds['capital'], signals, cap_vol) if 'capital' in creds else {}
    r_etoro = exec_etoro(creds, signals)
    summary = {'timestamp': run_ts, 'mode': 'weekend_crypto', 'signals': signals, 'ftmo': r_ftmo, 'capital': r_cap, 'etoro': r_etoro}
    out = LOGDIR / f"weekend_loop_{run_ts}.json"
    out.write_text(json.dumps(summary, indent=2, default=str))
    log(f"FTMO {len(r_ftmo.get('filled',[]))} CAP {len(r_cap.get('filled',[]))} eToro {r_etoro}")
    log(f"report -> {out}")
    return summary

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log(f"FATAL {traceback.format_exc()}"); sys.exit(1)