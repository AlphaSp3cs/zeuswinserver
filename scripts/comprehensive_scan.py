#!/usr/bin/env python3
"""
Comprehensive multi-market scanner with prediction markets, multi-TF analysis,
technical indicators, analyst targets, correlations, and scan-to-scan tracking.
"""
import json, datetime, sqlite3, os, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import MetaTrader5 as mt5
import yfinance as yf

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
WORKFLOW = BASE / 'workflow'
SCANDATA = BASE / 'scandata'
HTF_DB = BASE / 'htf' / 'htf_scan.db'
SCAN_STATE_DB = BASE / 'workflow' / 'scan_state.db'
ANALYST_CACHE = BASE / 'workflow' / 'analyst_targets_cache.json'

BROKER_PATHS = {
    'capital': r"C:\Program Files\Capital.com MetaTrader 5\terminal64.exe",
    'ftmo': r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe",
}

# Comprehensive universe: stocks, ETFs, indices, forex, commodities, crypto, prediction markets
UNIVERSE = {
    # US Large Cap Stocks
    'AAPL': 'Stocks', 'MSFT': 'Stocks', 'AMZN': 'Stocks', 'GOOGL': 'Stocks', 'META': 'Stocks',
    'NVDA': 'Stocks', 'TSLA': 'Stocks', 'JPM': 'Stocks', 'V': 'Stocks', 'JNJ': 'Stocks',
    'WMT': 'Stocks', 'PG': 'Stocks', 'MA': 'Stocks', 'UNH': 'Stocks', 'HD': 'Stocks',
    'DIS': 'Stocks', 'BAC': 'Stocks', 'XOM': 'Stocks', 'PFE': 'Stocks', 'KO': 'Stocks',
    # US Mid/Small Cap
    'AMD': 'Stocks', 'INTC': 'Stocks', 'SQ': 'Stocks', 'PLTR': 'Stocks', 'COIN': 'Stocks',
    'RKLB': 'Stocks', 'SOFI': 'Stocks', 'HOOD': 'Stocks', 'RDDT': 'Stocks', 'ARM': 'Stocks',
    # ETFs
    'SPY': 'ETFs', 'QQQ': 'ETFs', 'IWM': 'ETFs', 'DIA': 'ETFs', 'VOO': 'ETFs',
    'VTI': 'ETFs', 'ARKK': 'ETFs', 'XLF': 'ETFs', 'XLK': 'ETFs', 'XLE': 'ETFs',
    'GLD': 'ETFs', 'SLV': 'ETFs', 'TLT': 'ETFs', 'HYG': 'ETFs', 'LQD': 'ETFs',
    'EEM': 'ETFs', 'EFA': 'ETFs', 'EMB': 'ETFs', 'MUB': 'ETFs', 'TIP': 'ETFs',
    # Indices
    '^DJI': 'Indices', '^IXIC': 'Indices', '^GSPC': 'Indices', '^RUT': 'Indices',
    '^VIX': 'Indices', '^VXN': 'Indices', 'DX-Y.NYB': 'Indices',
    'US30': 'Indices', 'US100': 'Indices', 'US500': 'Indices', 'DXY': 'Indices',
    '^FTSE': 'Indices', '^GDAXI': 'Indices', '^FCHI': 'Indices', '^IBEX': 'Indices',
    '^AEX': 'Indices', '^SSMI': 'Indices', '^STOXX50E': 'Indices',
    '^N225': 'Indices', '^HSI': 'Indices', '^AXJO': 'Indices', '^STI': 'Indices',
    'ES=F': 'Indices', 'NQ=F': 'Indices', 'YM=F': 'Indices', 'RTY=F': 'Indices',
    # Forex - MT5 symbols
    'EURUSD': 'Forex', 'GBPUSD': 'Forex', 'USDJPY': 'Forex', 'AUDUSD': 'Forex',
    'USDCAD': 'Forex', 'USDCHF': 'Forex', 'NZDUSD': 'Forex',
    'EURJPY': 'Forex', 'EURGBP': 'Forex', 'GBPJPY': 'Forex',
    'AUDJPY': 'Forex', 'AUDCAD': 'Forex', 'CADJPY': 'Forex',
    'CHFJPY': 'Forex', 'NZDJPY': 'Forex', 'EURCHF': 'Forex', 'EURCAD': 'Forex',
    'EURAUD': 'Forex', 'GBPCHF': 'Forex', 'GBPAUD': 'Forex', 'GBPCAD': 'Forex',
    'GBPNZD': 'Forex', 'NZDCHF': 'Forex', 'NZDCAD': 'Forex',
    'USDTRY': 'Forex', 'USDZAR': 'Forex', 'USDMXN': 'Forex', 'USDCNY': 'Forex',
    'USDSGD': 'Forex', 'USDHKD': 'Forex', 'USDSEK': 'Forex', 'USDNOK': 'Forex',
    # Precious Metals
    'XAUUSD': 'Precious_Metals', 'XAGUSD': 'Precious_Metals', 'GC=F': 'Precious_Metals', 'SI=F': 'Precious_Metals',
    # Metals
    'HG=F': 'Metals', 'PL=F': 'Metals', 'ALI=F': 'Metals',
    # Energy
    'CL=F': 'Energy', 'NG=F': 'Energy', 'BRENT=F': 'Energy',
    # Crypto
    'BTC-USD': 'Crypto', 'ETH-USD': 'Crypto', 'SOL-USD': 'Crypto', 'XRP-USD': 'Crypto',
    'AVAX-USD': 'Crypto', 'LINK-USD': 'Crypto', 'ADA-USD': 'Crypto', 'DOGE-USD': 'Crypto',
    'BNB-USD': 'Crypto', 'MATIC-USD': 'Crypto', 'DOT-USD': 'Crypto', 'UNI-USD': 'Crypto',
    # Prediction Markets (Polymarket slugs)
    'polymarket_btc_100k_2025': 'Prediction_Markets',
    'polymarket_eth_10k_2025': 'Prediction_Markets',
    'polymarket_fed_rate_cut_2025': 'Prediction_Markets',
    'polymarket_spy_600_2025': 'Prediction_Markets',
    'polymarket_trump_2024': 'Prediction_Markets',
    'kalshi_fed_rate_jan': 'Prediction_Markets',
    'kalshi_btc_100k': 'Prediction_Markets',
    'kalshi_spx_6000': 'Prediction_Markets',
}

SECTOR_BROKER = {
    'Stocks': ['IBKR', 'ALPACA'],
    'ETFs': ['IBKR', 'ALPACA'],
    'Indices': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Forex': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Precious_Metals': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Metals': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Energy': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Crypto': ['KRAKEN', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Prediction_Markets': ['POLYMARKET', 'KALSHI'],
}

BROKER_ONLY = {
    'US30', 'US100', 'US500', 'DXY',
    'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD',
    'EURJPY', 'EURGBP', 'GBPJPY', 'AUDJPY', 'AUDCAD', 'CADJPY',
    'CHFJPY', 'NZDJPY', 'EURCHF', 'EURCAD', 'EURAUD', 'GBPCHF', 'GBPAUD',
    'GBPCAD', 'GBPNZD', 'NZDCHF', 'NZDCAD',
    'USDTRY', 'USDZAR', 'USDMXN', 'USDCNY', 'USDSGD', 'USDHKD', 'USDSEK', 'USDNOK',
    'XAUUSD', 'XAGUSD',
}

YF_DELISTED = {'^GDAXI', '^AXJO', '^STI'}

def init_mt5():
    for name, path in BROKER_PATHS.items():
        try:
            mt5.shutdown()
        except Exception:
            pass
        ok = mt5.initialize(path)
        if ok:
            return True
    return False

def fetch_broker(symbol, timeframe=mt5.TIMEFRAME_D1, count=200):
    for name, path in BROKER_PATHS.items():
        try:
            mt5.shutdown()
        except Exception:
            pass
        ok = mt5.initialize(path)
        if not ok:
            continue
        try:
            info = mt5.symbol_info(symbol)
            if not info or not getattr(info, 'visible', False):
                continue
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            if rates is None or len(rates) < 20:
                continue
            df = pd.DataFrame(rates)
            df = df.rename(columns={c: c.lower() for c in df.columns})
            if 'volume' not in df.columns:
                for candidate in ['tick_volume', 'real_volume']:
                    if candidate in df.columns:
                        df = df.rename(columns={candidate: 'volume'})
                        break
            df = df[['open', 'high', 'low', 'close', 'volume']].dropna(subset=['close'])
            return df
        except Exception:
            continue
    return pd.DataFrame()

def fetch_yf_tf(symbol, interval='1h', period='7d'):
    """Fetch yfinance data for multi-timeframe analysis."""
    import yfinance as yf
    try:
        df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False, threads=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            try:
                df = df.xs(symbol, level=1, axis=1)
                if isinstance(df, pd.Series):
                    df = df.to_frame()
            except Exception:
                try:
                    df = df.droplevel(0, axis=1)
                except Exception:
                    return pd.DataFrame()
        df = df.rename(columns=str.lower)
        needed = {'open', 'high', 'low', 'close'}
        if not needed.issubset(set(df.columns)):
            return pd.DataFrame()
        cols = ['open', 'high', 'low', 'close'] + (['volume'] if 'volume' in df.columns else [])
        df = df[cols].dropna(subset=['close'])
        return df
    except Exception:
        return pd.DataFrame()

def trend_alignment_yf(symbol):
    """Multi-timeframe trend alignment using yfinance for stocks/ETFs/crypto."""
    timeframes = [
        ('1H', '1h', '7d'),
        ('4H', '4h', '30d'),
        ('1D', '1d', '60d'),
        ('1W', '1wk', '2y'),
    ]
    trends = {}
    for label, interval, period in timeframes:
        df = fetch_yf_tf(symbol, interval, period)
        if df.empty or len(df) < 20:
            continue
        closes = df['close'].values
        last = float(closes[-1])
        sma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
        sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
        if sma20 and sma50 and last:
            if last > sma20 > sma50:
                trends[label] = 'BULL'
            elif last < sma20 < sma50:
                trends[label] = 'BEAR'
            else:
                trends[label] = 'MIXED'
        elif sma20 and last:
            if last > sma20:
                trends[label] = 'BULL'
            elif last < sma20:
                trends[label] = 'BEAR'
            else:
                trends[label] = 'MIXED'
        else:
            trends[label] = 'MIXED'
    return trends

def fetch_yf(symbol, period='60d', interval='1d'):
    """Fetch yfinance daily data."""
    return fetch_yf_tf(symbol, interval=interval, period=period)

def fetch_data(symbol):
    if symbol in BROKER_ONLY or symbol in YF_DELISTED:
        return fetch_broker(symbol), 'broker'
    df = fetch_yf(symbol)
    if not df.empty and len(df) >= 20:
        return df, 'yfinance'
    df = fetch_broker(symbol)
    return df, 'broker' if not df.empty else 'none'

def fetch_prediction_market(symbol):
    """Fetch prediction market data from Polymarket/Kalshi."""
    try:
        if symbol.startswith('polymarket_'):
            # Search Polymarket for relevant markets
            r = requests.get('https://clob.polymarket.com/markets', timeout=10, params={'limit': 100})
            if r.status_code == 200:
                markets = r.json().get('data', [])
                # Map symbol to market
                market_name = symbol.replace('polymarket_', '').replace('_', ' ').title()
                for m in markets:
                    if market_name.lower() in m.get('question', '').lower():
                        price = m.get('last_price', m.get('best_bid', 0.5))
                        return {
                            'last': price,
                            'volume': m.get('volume', 0),
                            'source': 'polymarket',
                            'question': m.get('question', ''),
                        }
        elif symbol.startswith('kalshi_'):
            # Kalshi requires auth, return placeholder
            return {'last': None, 'source': 'kalshi_auth_required', 'question': symbol}
    except Exception as e:
        print(f'  Prediction market fetch error for {symbol}: {e}')
    return {'last': None, 'source': 'none'}

def fetch_whale_activity(symbol, sector):
    """Detect whale buy/sell activity from volume spikes and large transactions."""
    whale_signal = None
    whale_score = 0
    
    try:
        if sector == 'Crypto':
            # Use yfinance volume data for crypto whale detection
            df = fetch_yf_tf(symbol, '1h', '7d')
            if not df.empty and 'volume' in df.columns and len(df) > 5:
                volumes = df['volume'].values
                avg_vol = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
                current_vol = volumes[-1]
                vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0
                
                # Volume spike > 3x average = whale activity
                if vol_ratio > 3.0:
                    whale_score = min(10, int(vol_ratio * 2))
                    price_change = df['close'].pct_change().iloc[-1] * 100
                    whale_signal = 'WHALE_BUY' if price_change > 0 else 'WHALE_SELL'
                elif vol_ratio > 2.0:
                    whale_score = 5
                    price_change = df['close'].pct_change().iloc[-1] * 100
                    whale_signal = 'WHALE_BUY' if price_change > 0 else 'WHALE_SELL'
        
        elif sector in ['Forex', 'Precious_Metals', 'Metals', 'Energy']:
            # Use MT5 tick volume for forex/metals whale detection
            for name, path in BROKER_PATHS.items():
                try:
                    mt5.shutdown()
                except Exception:
                    pass
                ok = mt5.initialize(path)
                if not ok:
                    continue
                
                info = mt5.symbol_info(symbol)
                if not info or not getattr(info, 'visible', False):
                    continue
                
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 24)
                if rates is not None and len(rates) > 5:
                    df = pd.DataFrame(rates)
                    df = df.rename(columns={c: c.lower() for c in df.columns})
                    
                    if 'volume' in df.columns or 'tick_volume' in df.columns:
                        vol_col = 'volume' if 'volume' in df.columns else 'tick_volume'
                        volumes = df[vol_col].values
                        avg_vol = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
                        current_vol = volumes[-1]
                        vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0
                        
                        if vol_ratio > 2.5:
                            whale_score = min(10, int(vol_ratio * 2))
                            price_change = df['close'].pct_change().iloc[-1] * 100
                            whale_signal = 'WHALE_BUY' if price_change > 0 else 'WHALE_SELL'
                    break
    except Exception as e:
        print(f'  Whale activity error for {symbol}: {e}')
    
    return {'whale_signal': whale_signal, 'whale_score': whale_score}

def fetch_analyst_targets(symbol):
    """Fetch analyst price targets from yfinance."""
    targets = {'target_price': None, 'target_high': None, 'target_low': None, 
               'analyst_count': 0, 'rating': None, 'recommendation_mean': None}
    
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # Target prices
        targets['target_price'] = info.get('targetMeanPrice', info.get('targetPrice', None))
        targets['target_high'] = info.get('targetHighPrice', None)
        targets['target_low'] = info.get('targetLowPrice', None)
        targets['target_median'] = info.get('targetMedianPrice', None)
        
        # Analyst rating
        targets['rating'] = info.get('recommendationKey', None)
        targets['recommendation_mean'] = info.get('recommendationMean', None)
        
        # Analyst count from recent recommendations
        try:
            rec = ticker.recommendations
            if rec is not None and not rec.empty:
                latest = rec.iloc[0]
                targets['analyst_count'] = sum([
                    int(latest.get('strongBuy', 0)),
                    int(latest.get('buy', 0)),
                    int(latest.get('hold', 0)),
                    int(latest.get('sell', 0)),
                    int(latest.get('strongSell', 0)),
                ])
        except Exception:
            pass
    except Exception as e:
        print(f'  Analyst target fetch error for {symbol}: {e}')
    
    return targets

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    ag = np.mean(gains[:period])
    al = np.mean(losses[:period])
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al <= 0:
        return 100.0 if ag > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + ag / al)

def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    tr1 = highs[1:] - lows[1:]
    tr2 = np.abs(highs[1:] - closes[:-1])
    tr3 = np.abs(lows[1:] - closes[:-1])
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    return float(np.mean(tr[-period:]))

def bollinger_bands(closes, period=20, std_dev=2.0):
    if len(closes) < period:
        return None, None, None
    sma = float(np.mean(closes[-period:]))
    std = float(np.std(closes[-period:]))
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    return upper, sma, lower

def trend_alignment(symbol, timeframes=None):
    """Check trend on 1H, 4H, 1D, 1W. Returns dict with trend per timeframe."""
    if timeframes is None:
        timeframes = [
            (mt5.TIMEFRAME_H1, '1H'),
            (mt5.TIMEFRAME_H4, '4H'),
            (mt5.TIMEFRAME_D1, '1D'),
            (mt5.TIMEFRAME_W1, '1W'),
        ]
    
    trends = {}
    for tf, label in timeframes:
        df = fetch_broker(symbol, timeframe=tf, count=60)
        if df.empty or len(df) < 20:
            continue
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        last = float(closes[-1])
        sma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
        sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
        
        # Determine trend
        if sma20 and sma50 and last:
            if last > sma20 > sma50:
                trends[label] = 'BULL'
            elif last < sma20 < sma50:
                trends[label] = 'BEAR'
            else:
                trends[label] = 'MIXED'
        else:
            trends[label] = 'MIXED'
    
    return trends

def correlation_score(symbol, all_data):
    """Calculate correlation with other assets in the scan."""
    if symbol not in all_data or len(all_data.get(symbol, [])) < 20:
        return 0.0
    
    symbol_prices = pd.Series(all_data[symbol])
    correlations = []
    
    for other_symbol, other_prices in all_data.items():
        if other_symbol == symbol or len(other_prices) < 20:
            continue
        other_series = pd.Series(other_prices)
        if len(symbol_prices) != len(other_series):
            continue
        corr = symbol_prices.corr(other_series)
        if not np.isnan(corr):
            correlations.append(abs(corr))
    
    if not correlations:
        return 0.0
    
    avg_corr = np.mean(correlations)
    return round(avg_corr * 10, 2)  # Scale to 0-10

def load_scan_state():
    """Load scan-to-scan state for trend tracking."""
    if not SCAN_STATE_DB.exists():
        return {}
    try:
        con = sqlite3.connect(str(SCAN_STATE_DB))
        cur = con.cursor()
        cur.execute('SELECT symbol, last_trend, last_rsi, last_conviction, scan_count, last_scan_time FROM scan_state')
        state = {}
        for row in cur.fetchall():
            state[row[0]] = {
                'last_trend': row[1],
                'last_rsi': row[2],
                'last_conviction': row[3],
                'scan_count': row[4],
                'last_scan_time': row[5]
            }
        con.close()
        return state
    except Exception:
        return {}

def save_scan_state(state):
    """Save scan-to-scan state."""
    try:
        con = sqlite3.connect(str(SCAN_STATE_DB))
        cur = con.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS scan_state (
                symbol TEXT PRIMARY KEY,
                last_trend TEXT,
                last_rsi REAL,
                last_conviction REAL,
                scan_count INTEGER,
                last_scan_time TEXT
            )
        ''')
        for symbol, data in state.items():
            cur.execute('''
                INSERT OR REPLACE INTO scan_state 
                (symbol, last_trend, last_rsi, last_conviction, scan_count, last_scan_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (symbol, data['last_trend'], data['last_rsi'], data['last_conviction'], 
                  data['scan_count'], data['last_scan_time']))
        con.commit()
        con.close()
    except Exception as e:
        print(f'Warning: could not save scan state: {e}')

# Main comprehensive scan
def comprehensive_scan(session='nightshift'):
    print(f'=== Comprehensive {session} Scan ===')
    
    # Define session scopes
    SESSION_SCOPE = {
        'nightshift': ['Indices', 'Forex', 'Precious_Metals', 'Metals', 'Energy', 'Crypto', 'Prediction_Markets'],
        'dayshift': ['Stocks', 'ETFs', 'Indices', 'Forex', 'Precious_Metals', 'Metals', 'Energy', 'Crypto', 'Prediction_Markets'],
        'full': ['Stocks', 'ETFs', 'Indices', 'Forex', 'Precious_Metals', 'Metals', 'Energy', 'Crypto', 'Prediction_Markets'],
    }
    
    allowed_sectors = SESSION_SCOPE.get(session, SESSION_SCOPE['nightshift'])
    print(f'Session scope: {session}')
    print(f'Allowed sectors: {allowed_sectors}')
    
    # Filter universe by session scope
    filtered_universe = {symbol: sector for symbol, sector in UNIVERSE.items() if sector in allowed_sectors}
    print(f'Universe: {len(filtered_universe)} symbols (from {len(UNIVERSE)} total)')
    print(f'Started: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n')
    
    # Initialize
    scan_state = load_scan_state()
    price_history = {}
    results = {
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'session': session,
        'universe_size': len(UNIVERSE),
        'sectors': {},
        'viable_setups': [],
        'prediction_markets': [],
        'sector_trends': {},
        'correlations': {},
        'scan_to_scan': {},
    }
    
    # Initialize MT5
    mt5_ready = init_mt5()
    print(f'MT5 ready: {mt5_ready}\n')
    
    # First pass: fetch data
    print('Fetching market data...')
    for symbol, sector in filtered_universe.items():
        brokers = SECTOR_BROKER.get(sector, [])
        
        # Prediction markets
        if sector == 'Prediction_Markets':
            pm_data = fetch_prediction_market(symbol)
            if pm_data.get('last'):
                rec = {
                    'symbol': symbol,
                    'sector': sector,
                    'broker_routing': ['POLYMARKET', 'KALSHI'],
                    'data_source': pm_data.get('source', 'prediction_market'),
                    'last': pm_data['last'],
                    'rsi': None,
                    'atr': None,
                    'sma20': None,
                    'sma50': None,
                    'bollinger_upper': None,
                    'bollinger_middle': None,
                    'bollinger_lower': None,
                    'trend': {},
                    'analyst_target': None,
                    'analyst_rating': None,
                    'analyst_count': 0,
                    'backtest_grade': None,
                    'backtest_score': None,
                    'backtested': False,
                    'conviction': 0.0,
                    'viable': True,
                    'reason': ['PREDICTION_MARKET'],
                    'hold_time_estimate': '1-30 days',
                    'volume': pm_data.get('volume', 0),
                    'question': pm_data.get('question', ''),
                }
                results['sectors'][symbol] = rec
                results['prediction_markets'].append(rec)
                results['viable_setups'].append(rec)
                print(f'  ✓ {symbol:30} {sector:20} last={pm_data["last"]:.4f} src={pm_data.get("source", "?")}')
            continue
        
        # Regular assets
        df, source = fetch_data(symbol)
        if df.empty or len(df) < 20:
            results['sectors'][symbol] = {
                'symbol': symbol, 'sector': sector, 'broker_routing': brokers,
                'data_source': source, 'status': 'NO_DATA'
            }
            continue
        
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        last = float(closes[-1])
        r = rsi(closes)
        a = atr(highs, lows, closes)
        sma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
        sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
        bb_upper, bb_middle, bb_lower = bollinger_bands(closes)
        
        # Store price history for correlation
        price_history[symbol] = closes[-60:] if len(closes) >= 60 else closes
        
        # Multi-timeframe trend alignment
        if symbol in BROKER_ONLY:
            trends = trend_alignment(symbol)
        elif sector in ['Stocks', 'ETFs', 'Crypto']:
            trends = trend_alignment_yf(symbol)
        else:
            trends = {}
        
        # Analyst targets (only for stocks/ETFs)
        analyst = {'target_price': None, 'rating': None, 'analyst_count': 0}
        if sector in ['Stocks', 'ETFs']:
            analyst = fetch_analyst_targets(symbol)
        
        # Whale activity detection
        whale = fetch_whale_activity(symbol, sector)
        
        rec = {
            'symbol': symbol,
            'sector': sector,
            'broker_routing': brokers,
            'data_source': source,
            'last': round(last, 6),
            'rsi': round(r, 2),
            'atr': round(a, 6) if a is not None else None,
            'sma20': round(sma20, 6) if sma20 else None,
            'sma50': round(sma50, 6) if sma50 else None,
            'bollinger_upper': round(bb_upper, 6) if bb_upper else None,
            'bollinger_middle': round(bb_middle, 6) if bb_middle else None,
            'bollinger_lower': round(bb_lower, 6) if bb_lower else None,
            'trend': trends,
            'analyst_target': analyst.get('target_price'),
            'analyst_rating': analyst.get('rating'),
            'analyst_count': analyst.get('analyst_count', 0),
            'whale_activity': whale,
            'backtest_grade': None,
            'backtest_score': None,
            'backtested': False,
            'conviction': 0.0,
            'viable': False,
            'reason': [],
            'hold_time_estimate': None,
        }
        results['sectors'][symbol] = rec
        print(f'  {symbol:12} {sector:20} last={last:10.4f} rsi={r:6.2f} src={source}')
    
    # Second pass: compute conviction and viability
    print('\nComputing conviction scores and multi-TF trends...')
    for symbol, rec in results['sectors'].items():
        if rec.get('status') == 'NO_DATA':
            continue
        
        r = rec.get('rsi', 50)
        a = rec.get('atr')
        last = rec.get('last')
        sma20 = rec.get('sma20')
        sma50 = rec.get('sma50')
        trends = rec.get('trend', {})
        
        # Conviction scoring
        score = 0.0
        
        # RSI component
        if r < 20:
            score += 10
        elif r < 30:
            score += 7
        elif r > 80:
            score += 10
        elif r > 70:
            score += 7
        elif r < 40:
            score += 3
        elif r > 60:
            score += 3
        
        # Multi-timeframe trend component
        tf_bull = sum(1 for t in trends.values() if t == 'BULL')
        tf_bear = sum(1 for t in trends.values() if t == 'BEAR')
        tf_count = len(trends)
        
        if tf_count > 0:
            if tf_bull == tf_count:
                score += 15  # All TFs bullish
            elif tf_bear == tf_count:
                score += 15  # All TFs bearish
            elif tf_bull >= 2:
                score += 10
            elif tf_bear >= 2:
                score += 10
            elif tf_bull >= 1 or tf_bear >= 1:
                score += 5
        
        # Bollinger Bands component
        bb_upper = rec.get('bollinger_upper')
        bb_lower = rec.get('bollinger_lower')
        if bb_upper and bb_lower and last:
            bb_width = (bb_upper - bb_lower) / rec.get('bollinger_middle', 1)
            if bb_width > 0.05:  # Wide bands = high volatility
                score += 5
            if last < bb_lower:
                score += 5  # Oversold
            elif last > bb_upper:
                score += 5  # Overbought
        
        # ATR component
        if a and last and last > 0:
            atr_pct = (a / last) * 100
            if atr_pct > 2.0:
                score += 5
            elif atr_pct > 1.0:
                score += 3
        
        # Analyst target component
        analyst_target = rec.get('analyst_target')
        if analyst_target and last:
            upside = ((analyst_target - last) / last) * 100
            if upside > 15:
                score += 10
            elif upside > 10:
                score += 7
            elif upside > 5:
                score += 5
        
        # Whale activity component
        whale = rec.get('whale_activity', {})
        whale_score = whale.get('whale_score', 0) if isinstance(whale, dict) else 0
        whale_signal = whale.get('whale_signal') if isinstance(whale, dict) else None
        score += whale_score
        
        # Correlation component
        corr_score = correlation_score(symbol, price_history)
        score += corr_score
        
        # Scan-to-scan momentum
        prev_state = scan_state.get(symbol, {})
        prev_trend = prev_state.get('last_trend')
        if prev_trend and trends:
            current_consensus = 'BULL' if tf_bull > tf_bear else 'BEAR' if tf_bear > tf_bull else 'MIXED'
            if current_consensus == prev_trend:
                score += 5  # Trend persistence bonus
        
        rec['conviction'] = round(score, 2)
        
        # Viability check
        viable = False
        reason = []
        
        if r < 30:
            viable = True
            reason.append('RSI_OVERSOLD')
        elif r > 70:
            viable = True
            reason.append('RSI_OVERBOUGHT')
        
        if tf_count > 0 and tf_bull == tf_count:
            viable = True
            reason.append('ALL_TF_BULL')
        elif tf_count > 0 and tf_bear == tf_count:
            viable = True
            reason.append('ALL_TF_BEAR')
        
        if bb_lower and last < bb_lower:
            viable = True
            reason.append('BB_OVERSOLD')
        elif bb_upper and last > bb_upper:
            viable = True
            reason.append('BB_OVERBOUGHT')
        
        if analyst_target and last:
            upside = ((analyst_target - last) / last) * 100
            if upside > 10:
                viable = True
                reason.append('ANALYST_UPGRADE')
        
        # Whale activity boost
        if whale_score >= 5:
            viable = True
            reason.append(f'WHALE_{whale_signal}' if whale_signal else 'WHALE_ACTIVITY')
        
        if a is None or a == 0:
            # Keep viable if we have TF alignment, but remove RSI/BB reasons
            if 'ALL_TF_BULL' not in reason and 'ALL_TF_BEAR' not in reason and 'ANALYST_UPGRADE' not in reason:
                viable = False
            reason = [x for x in reason if x not in ('RSI_OVERSOLD', 'RSI_OVERBOUGHT', 'BB_OVERSOLD', 'BB_OVERBOUGHT')]
        
        rec['viable'] = viable
        rec['reason'] = reason
        
        # Calculate entry, SL, TP
        if viable:
            entry = last
            # Determine trade direction from reasons
            if 'RSI_OVERSOLD' in reason or 'BB_OVERSOLD' in reason or 'ALL_TF_BEAR' in reason or 'WHALE_BUY' in reason:
                side = 'LONG'
            elif 'RSI_OVERBOUGHT' in reason or 'BB_OVERBOUGHT' in reason or 'ALL_TF_BULL' in reason or 'WHALE_SELL' in reason:
                side = 'SHORT'
            else:
                side = 'LONG' if tf_bull >= tf_bear else 'SHORT'
            
            rec['side'] = side
            
            if a:
                if side == 'LONG':
                    sl = entry - a
                    tp1 = entry + a
                    tp2 = entry + (2 * a)
                else:
                    sl = entry + a
                    tp1 = entry - a
                    tp2 = entry - (2 * a)
                
                rec['entry'] = round(entry, 6)
                rec['sl'] = round(sl, 6)
                rec['tp1'] = round(tp1, 6)
                rec['tp2'] = round(tp2, 6)
                
                # Hold time estimate based on ATR and timeframe
                if a and last:
                    atr_pct = (a / last) * 100
                    if atr_pct > 2.0:
                        rec['hold_time_estimate'] = '1-3 days'
                    elif atr_pct > 1.0:
                        rec['hold_time_estimate'] = '4-24h'
                    else:
                        rec['hold_time_estimate'] = '1-7 days'
            
            results['viable_setups'].append(rec)
        
        # Update scan state
        current_consensus = 'BULL' if tf_bull > tf_bear else 'BEAR' if tf_bear > tf_bull else 'MIXED'
        scan_state[symbol] = {
            'last_trend': current_consensus,
            'last_rsi': r,
            'last_conviction': rec['conviction'],
            'scan_count': prev_state.get('scan_count', 0) + 1,
            'last_scan_time': datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
    
    # Third pass: compute correlations
    print('\nComputing cross-asset correlations...')
    correlations = {}
    for symbol in list(price_history.keys())[:30]:  # Limit to 30 for performance
        correlations[symbol] = correlation_score(symbol, price_history)
    results['correlations'] = correlations
    
    # Sector trends - use ALL assets with trend data
    print('\nComputing sector trends...')
    sector_trends = {}
    for sector in UNIVERSE.values():
        sector_trends[sector] = {'bull': 0, 'bear': 0, 'mixed': 0, 'total': 0}
    
    for rec in results['sectors'].values():
        if not isinstance(rec, dict) or rec.get('status') == 'NO_DATA':
            continue
        sector = rec.get('sector', 'Unknown')
        trends = rec.get('trend', {})
        if trends:
            tf_bull = sum(1 for t in trends.values() if t == 'BULL')
            tf_bear = sum(1 for t in trends.values() if t == 'BEAR')
            if tf_bull > tf_bear:
                sector_trends[sector]['bull'] += 1
            elif tf_bear > tf_bull:
                sector_trends[sector]['bear'] += 1
            else:
                sector_trends[sector]['mixed'] += 1
            sector_trends[sector]['total'] += 1
    
    results['sector_trends'] = sector_trends
    
    # Sort viable setups by conviction
    results['viable_setups'] = sorted(results['viable_setups'], key=lambda x: x['conviction'], reverse=True)
    results['viable_count'] = len(results['viable_setups'])
    results['scanned_count'] = len([k for k, v in results['sectors'].items() if v.get('status') != 'NO_DATA'])
    
    # Save scan state
    save_scan_state(scan_state)
    
    # Write output with numpy-safe serialization
    class _NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)
    
    out_file = WORKFLOW / f'comprehensive_scan_{datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'
    out_file.write_text(json.dumps(results, indent=2, cls=_NumpyEncoder), encoding='utf-8')
    
    print(f'\n=== Scan Complete ===')
    print(f'Wrote: {out_file}')
    print(f'Scanned: {results["scanned_count"]}')
    print(f'Viable: {results["viable_count"]}')
    print(f'Prediction markets: {len(results["prediction_markets"])}')
    print('\nTop 20 setups:')
    for i, x in enumerate(results['viable_setups'][:20], 1):
        print(f"{i:2}. {x['symbol']:12} {x['sector']:20} conv={x['conviction']:6.2f} rsi={x['rsi']:6.2f} side={x.get('side','?')} entry={x.get('entry','?')} sl={x.get('sl','?')} tp={x.get('tp1','?')} src={x['data_source']}")
    
    print('\nSector trends:')
    for sector, counts in sector_trends.items():
        if counts['total'] > 0:
            print(f"  {sector:20}: BULL={counts['bull']} BEAR={counts['bear']} MIXED={counts['mixed']} total={counts['total']}")
    
    return results

if __name__ == '__main__':
    session = 'nightshift'
    if len(__import__('sys').argv) > 1:
        session = __import__('sys').argv[1]
    comprehensive_scan(session)
