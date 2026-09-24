#!/usr/bin/env python3
"""Local fallback backfill for universal data gaps when Syndicate API is unreachable."""
import json, time, sys, os
from pathlib import Path
from datetime import datetime, timezone

try:
    import yfinance as yf
    import pandas as pd
except Exception as e:
    print('Missing yfinance/pandas:', e)
    sys.exit(1)

try:
    import ccxt
except Exception as e:
    print('Missing ccxt:', e)
    sys.exit(1)

DAILY_DIR = Path('data/daily')
DAILY_DIR.mkdir(exist_ok=True)
QUOTE_PATH = Path('data/latest_quotes.json')
QUOTE_PATH.parent.mkdir(exist_ok=True)
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
    last = bars[-1]['t'] if bars else None
    quotes[symbol] = {
        'last': bars[-1]['c'] if bars else None,
        'date': last,
        'source': source,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
    }
    return True

def yfinance_fetch(symbol: str):
    source = 'yfinance'
    sym = symbol
    # Crypto pairs
    if sym in {'BTC','ETH','SOL','BNB','XRP','ADA','AVAX','DOGE','DOT','LINK','MATIC','POL','UNI','ATOM','LTC','FIL','APT','ARB','OP','SUI','SEI','INJ','TIA','NEAR','ETC','AAVE','MKR','SNX','COMP','SUSHI','CRV','PEPE','SHIB','WIF','BONK','FLOKI','RNDR','FET','AGIX','ARKM','WLD','TIA','INJ','PYTH','JTO','OSMO','KAVA','RUNE','THETA','IMX','BLUR','DYDX','GMX','LDO','RPL','ENS','LQTY','YFI','1INCH','ZRX','BAL','KNC','BNT','C98','COTI','MASK','MOVR','POND','REEF','SAND','MANA','GALA','AXS','ALICE','TLM','SYS','NKN','HNT','API3','BADGER','KP3R','MIR','SRM','FTT','RAY','STEP','SUN','SUSHI'}:
        sym = f'{symbol}-USD'
    # Special cases
    elif symbol in {'BRK.A','BRK.B'}:
        pass
    else:
        sym = symbol
    ticker = yf.Ticker(sym)
    hist = ticker.history(period='2y', interval='1d', actions=False, auto_adjust=False)
    if hist is None or hist.empty:
        # Try with alternate
        return None
    return hist

def ccxt_fetch(symbol: str):
    # Use BinanceUS for non-US restricted symbols; fallback Coinbase/Bybit public
    exchanges = ['binanceus', 'coinbase', 'bybit']
    for ex_name in exchanges:
        try:
            ex = getattr(ccxt, ex_name)()
            markets = ex.load_markets()
            # Try exact symbol
            if symbol in markets:
                ohlcv = ex.fetch_ohlcv(symbol, timeframe='1d', limit=730)
                if ohlcv:
                    df = pd.DataFrame(ohlcv, columns=['ts','Open','High','Low','Close','Volume'])
                    df['Date'] = pd.to_datetime(df['ts'], unit='ms')
                    df = df.set_index('Date')[['Open','High','Low','Close','Volume']]
                    return df, ex_name
            # Try symbol/quote heuristics
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
    priority = inv.get('priority_samples', [])
    print(f'Priority targets: {len(priority)}')
    done = ok = fail = skip = 0
    for symbol in priority:
        if not symbol or '/' in symbol:
            skip += 1
            continue
        path = DAILY_DIR / f'{sanitize(symbol)}_daily.json'
        if path.exists():
            done += 1
            continue
        df = None
        source = None
        try:
            df = yfinance_fetch(symbol)
            source = 'yfinance'
        except Exception:
            df = None
        if df is None or df.empty:
            try:
                df, source = ccxt_fetch(symbol)
            except Exception:
                df = None
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
        if done % 50 == 0 or done == len(priority):
            print(f'  Progress {done}/{len(priority)} | ok={ok} fail={fail} skip={skip}')
        time.sleep(0.12)
    QUOTE_PATH.write_text(json.dumps(quotes, indent=2))
    print('Backfill done')
    print('ok=',ok,'fail=',fail,'skip=',skip)

if __name__ == '__main__':
    main()
