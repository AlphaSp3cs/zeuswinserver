#!/usr/bin/env python3
"""Local fallback backfill v2 with broader symbol mapping and larger universe coverage."""
import json, time, sys
from pathlib import Path
from datetime import datetime, timezone

import yfinance as yf
import pandas as pd
import ccxt

DAILY_DIR = Path('data/daily')
DAILY_DIR.mkdir(exist_ok=True)
QUOTE_PATH = Path('data/latest_quotes.json')
quotes = {}
if QUOTE_PATH.exists():
    try:
        quotes = json.loads(QUOTE_PATH.read_text())
        if not isinstance(quotes, dict):
            quotes = {}
    except Exception:
        quotes = {}

def sanitize(symbol: str) -> str:
    return symbol.replace('/', '_').replace(':', '_').replace(' ', '_').replace('.', '_')

def save_daily(symbol: str, df: pd.DataFrame, source: str):
    if df is None or df.empty:
        return False
    bars = []
    for ts, row in df.iterrows():
        t = ts.strftime('%Y-%m-%d') if hasattr(ts, 'strftime') else str(ts)
        bars.append({
            't': t,
            'o': float(row['Open']),
            'h': float(row['High']),
            'l': float(row['Low']),
            'c': float(row['Close']),
            'v': float(row['Volume']) if 'Volume' in row and row['Volume'] == row['Volume'] else 0.0,
        })
    out = {
        'symbol': symbol,
        'interval': '1d',
        'count': len(bars),
        'source': source,
        'bars': bars,
    }
    path = DAILY_DIR / f'{sanitize(symbol)}_daily.json'
    path.write_text(json.dumps(out, indent=2))
    quotes[symbol] = {
        'last': bars[-1]['c'] if bars else None,
        'date': bars[-1]['t'] if bars else None,
        'source': source,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
    }
    return True

CRYPTO_CANDIDATES = {
    'BTC','ETH','SOL','BNB','XRP','ADA','AVAX','DOGE','DOT','LINK','MATIC','POL','UNI','ATOM','LTC','FIL',
    'APT','ARB','OP','SUI','SEI','INJ','TIA','NEAR','ETC','AAVE','MKR','SNX','COMP','SUSHI','CRV','PEPE',
    'SHIB','WIF','BONK','FLOKI','RNDR','FET','AGIX','ARKM','WLD','PYTH','JTO','OSMO','KAVA','RUNE','THETA',
    'IMX','BLUR','DYDX','GMX','LDO','RPL','ENS','LQTY','YFI','1INCH','ZRX','BAL','KNC','BNT','C98','COTI',
    'MASK','MOVR','POND','REEF','SAND','MANA','GALA','AXS','ALICE','TLM','SYS','NKN','HNT','API3','BADGER',
    'KP3R','MIR','SRM','FTT','RAY','STEP','SUN','GRT','ICP','HBAR','TON','ENA','EIGEN','NOT','USUAL','STRK',
    'ZK','MOVE','AEVO','JUP','DYM','TNSR','ETHFI','REZ','PIXEL','PORTAL','AXL','MAGIC','HIGH','TLOS','CELO',
    'ROSE','MOVR','GLMR','SDN','CFG','CTSI','SKL','RAD','BAND','TRB','DEXT','RBN','UMA','LRC'
}

def yf_fetch(symbol: str):
    candidates = []
    if symbol in CRYPTO_CANDIDATES:
        candidates.append(f'{symbol}-USD')
    elif len(symbol) == 6 and symbol.isalpha():
        candidates.extend([f'{symbol}=X', symbol])
    elif symbol in {'VIX','GC','SI','CL','NG','HG','PL','PA','ZC','ZW','ZS','ZL','KC','CT','SB','OJ','CC'}:
        candidates.append(f'{symbol}=F')
        if symbol in {'VIX','GC','SI','CL','NG'}:
            candidates.extend([f'^{symbol}=F', f'^{symbol}'])
    elif symbol in {'ES','NQ','YM','RTY'}:
        candidates.extend([f'^{symbol}', f'{symbol}=F'])
    else:
        candidates.append(symbol)
    for cand in list(dict.fromkeys(candidates)):
        try:
            ticker = yf.Ticker(cand)
            hist = ticker.history(period='2y', interval='1d', actions=False, auto_adjust=False)
            if hist is not None and not hist.empty:
                return hist, 'yfinance'
        except Exception:
            continue
    return None, None

def ccxt_fetch(symbol: str):
    exchanges = ['binanceus', 'coinbase', 'bybit']
    for ex_name in exchanges:
        try:
            ex = getattr(ccxt, ex_name)()
            markets = ex.load_markets()
            for quote in ['USD','USDT','BUSD','USDC']:
                pair = f'{symbol}/{quote}'
                if pair in markets:
                    ohlcv = ex.fetch_ohlcv(pair, timeframe='1d', limit=730)
                    if ohlcv:
                        df = pd.DataFrame(ohlcv, columns=['ts','Open','High','Low','Close','Volume'])
                        df['Date'] = pd.to_datetime(df['ts'], unit='ms')
                        df = df.set_index('Date')[['Open','High','Low','Close','Volume']]
                        return df, ex_name
        except Exception:
            continue
    return None, None

def main():
    inv_path = Path('universal_fill_gap_inventory_20260815.json')
    if not inv_path.exists():
        print('Run gap inventory first')
        sys.exit(1)
    inv = json.loads(inv_path.read_text())
    priority = inv.get('priority_samples', []) or []
    # Expand to full missing set if possible
    registry = {}
    for p in ['workflow/crypto_universe_20260809.json','workflow/full_market_universe.json','workflow/master_asset_universe.json','workflow/alpaca_tradeable_assets_20260812.json']:
        path = Path(p)
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        def extract_symbols(obj):
            out=[]
            if isinstance(obj,dict):
                for k,v in obj.items():
                    if isinstance(v,list):
                        if v and isinstance(v[0],str): out.extend(v)
                        elif v and isinstance(v[0],dict):
                            for item in v: out.extend(extract_symbols(item))
                    elif isinstance(v,dict): out.extend(extract_symbols(v))
            elif isinstance(obj,list):
                for item in obj:
                    if isinstance(item,dict):
                        s=item.get('symbol') or item.get('ticker') or item.get('sym')
                        if s: out.append(s)
            return out
        for s in extract_symbols(data):
            registry.setdefault(str(s), set()).add(path.name)
    have = {p.name.replace('_daily.json','') for p in DAILY_DIR.glob('*_daily.json')}
    if priority:
        missing = [s for s in priority if s not in have and s in registry]
    else:
        missing = [s for s in registry if s not in have]
    print(f'Priority targets: {len(missing)}')
    done = ok = fail = 0
    for symbol in missing:
        if not symbol or '/' in symbol:
            done += 1
            continue
        path = DAILY_DIR / f'{sanitize(symbol)}_daily.json'
        if path.exists() and path.stat().st_size > 100:
            done += 1
            continue
        df, source = yf_fetch(symbol)
        if df is None or df.empty:
            df, source = ccxt_fetch(symbol)
        if df is not None and not df.empty:
            try:
                save_daily(symbol, df, source)
                ok += 1
            except Exception as e:
                fail += 1
                print(f'  SAVE_FAIL {symbol}: {e}')
        else:
            fail += 1
        done += 1
        if done % 100 == 0 or done == len(missing):
            print(f'  Progress {done}/{len(missing)} | ok={ok} fail={fail}')
        time.sleep(0.12)
    QUOTE_PATH.write_text(json.dumps(quotes, indent=2))
    print('Backfill v2 done')
    print('ok=',ok,'fail=',fail,'total=',len(missing))

if __name__ == '__main__':
    main()
