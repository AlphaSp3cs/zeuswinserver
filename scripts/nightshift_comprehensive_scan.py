#!/usr/bin/env python3
"""
Comprehensive nightshift scan across all HTF universe symbols.
Includes: ATR, news sentiment, backtesting, conviction scoring.
Does NOT filter by broker executability, but records broker routing per sector.
"""
import json, datetime, sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
WORKFLOW = BASE / 'workflow'
HTF_DB = BASE / 'htf' / 'htf_scan.db'
OUT = WORKFLOW / f'nightshift_comprehensive_scan_{datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'

# Full HTF universe
UNIVERSE = {
    'BTC-USD': 'Crypto', 'ETH-USD': 'Crypto', 'SOL-USD': 'Crypto', 'XRP-USD': 'Crypto',
    'AVAX-USD': 'Crypto', 'LINK-USD': 'Crypto', 'ADA-USD': 'Crypto', 'DOGE-USD': 'Crypto',
    'EURUSD=X': 'Forex', 'GBPUSD=X': 'Forex', 'USDJPY=X': 'Forex', 'AUDUSD=X': 'Forex',
    'USDCAD=X': 'Forex', 'USDCHF=X': 'Forex', 'NZDUSD=X': 'Forex',
    'GC=F': 'Metals', 'SI=F': 'Metals', 'HG=F': 'Metals', 'PL=F': 'Metals',
    'CL=F': 'Energy', 'NG=F': 'Energy', 'BZ=F': 'Energy',
    'ZC=F': 'Agriculture', 'ZS=F': 'Agriculture', 'ZW=F': 'Agriculture', 'KC=F': 'Agriculture',
    'ES=F': 'Futures', 'NQ=F': 'Futures', 'YM=F': 'Futures', 'RTY=F': 'Futures',
    'ZN=F': 'Bonds', 'ZB=F': 'Bonds', 'TLT': 'Bonds', 'IEF': 'Bonds',
    'HYG': 'Bonds', 'LQD': 'Bonds', '^TNX': 'Bonds',
    '^GSPC': 'Indices', '^IXIC': 'Indices', '^RUT': 'Indices', '^VIX': 'Indices',
    '^FTSE': 'Indices', '^GDAXI': 'Indices', '^N225': 'Indices',
    'SPY': 'Options_Underlying', 'QQQ': 'Options_Underlying', 'IWM': 'Options_Underlying',
    'AAPL': 'Technology', 'MSFT': 'Technology', 'NVDA': 'Technology', 'AMD': 'Technology',
    'INTC': 'Technology', 'AVGO': 'Technology',
    'JPM': 'Financials', 'BAC': 'Financials', 'GS': 'Financials', 'BRK-B': 'Financials',
    'JNJ': 'Healthcare', 'PFE': 'Healthcare', 'UNH': 'Healthcare', 'LLY': 'Healthcare',
    'XOM': 'Energy_Equity', 'CVX': 'Energy_Equity', 'COP': 'Energy_Equity', 'SLB': 'Energy_Equity',
    'TSLA': 'Consumer_Disc', 'AMZN': 'Consumer_Disc', 'HD': 'Consumer_Disc', 'MCD': 'Consumer_Disc',
    'KO': 'Consumer_Staples', 'PEP': 'Consumer_Staples', 'WMT': 'Consumer_Staples', 'PG': 'Consumer_Staples',
    'CAT': 'Industrials', 'GE': 'Industrials', 'HON': 'Industrials', 'UPS': 'Industrials',
    'VNQ': 'Real_Estate', 'PLD': 'Real_Estate', 'AMT': 'Real_Estate',
    'NEE': 'Utilities', 'DUK': 'Utilities', 'SO': 'Utilities',
    'META': 'Communication', 'GOOGL': 'Communication', 'DIS': 'Communication', 'NFLX': 'Communication',
    'NUE': 'Materials', 'FCX': 'Materials', 'MP': 'Materials', 'AA': 'Materials',
}

SECTOR_BROKER = {
    'Crypto': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'KRAKEN', 'ALPACA'],
    'Forex': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Metals': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Energy': ['CAPITAL_RIGHT', 'IBKR'],
    'Agriculture': ['IBKR', 'CAPITAL_RIGHT'],
    'Futures': ['IBKR', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Bonds': ['IBKR', 'ALPACA'],
    'Indices': ['FTMO_LEFT', 'CAPITAL_RIGHT', 'IBKR'],
    'Options_Underlying': ['IBKR', 'ALPACA'],
    'Technology': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Financials': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Healthcare': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Energy_Equity': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Consumer_Disc': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Consumer_Staples': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Industrials': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Real_Estate': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Utilities': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Communication': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
    'Materials': ['IBKR', 'ALPACA', 'FTMO_LEFT', 'CAPITAL_RIGHT'],
}

# Load existing conviction/backtest data from HTF DB
CONVICTION_DB = {}
if HTF_DB.exists():
    try:
        con = sqlite3.connect(str(HTF_DB)); cur = con.cursor()
        cur.execute('SELECT symbol, side, tech_score, fund_score, news_score, backtest_score, conviction, grade, backtested, entry, sl, tp, rr FROM htf_conviction WHERE asof=(SELECT max(asof) FROM htf_conviction)')
        for row in cur.fetchall():
            CONVICTION_DB[row[0]] = {
                'side': row[1], 'tech_score': row[2], 'fund_score': row[3], 'news_score': row[4],
                'backtest_score': row[5], 'conviction': row[6], 'grade': row[7], 'backtested': bool(row[8]),
                'entry': row[9], 'sl': row[10], 'tp': row[11], 'rr': row[12]
            }
        con.close()
    except Exception as e:
        print('DB load warning', e)

# News helpers
POS = ['bullish', 'upgrade', 'growth', 'surge', 'rally', 'beat', 'outperform',
       'strong', 'gain', 'soar', 'breakthrough', 'record', 'win', 'approved']
NEG = ['bearish', 'downgrade', 'recession', 'crash', 'miss', 'underperform',
       'weak', 'drop', 'decline', 'plunge', 'fear', 'lawsuit', 'cut', 'warning']

def score_text(text):
    low = (text or '').lower()
    p = sum(low.count(w) for w in POS)
    n = sum(low.count(w) for w in NEG)
    if p > n:
        return min(100, 50 + p * 10 - n * 5), 'BULLISH'
    if n > p:
        return max(0, 50 - n * 10 + p * 5), 'BEARISH'
    return 50, 'NEUTRAL'

def load_symbol_map():
    path = WORKFLOW / f'news_symbol_map_{datetime.datetime.now(datetime.timezone.utc).date().isoformat()}.json'
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data.get('symbols', {}) if isinstance(data, dict) else {}
    except Exception:
        return {}

SYMBOL_MAP = load_symbol_map()

def news_for(symbol, sector):
    key = f"{symbol}|{sector}"
    if key in SYMBOL_MAP:
        rec = SYMBOL_MAP[key]
        if rec.get('headlines'):
            return rec.get('sentiment', 'NEUTRAL'), rec.get('score', 50), ' | '.join(rec.get('headlines', [])[:6])
    return 'NEUTRAL', 50, ''

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gs, ls = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gs.append(max(d, 0.0))
        ls.append(max(-d, 0.0))
    ag = sum(gs[:period]) / period
    al = sum(ls[:period]) / period
    for i in range(period, len(gs)):
        ag = (ag * (period - 1) + gs[i]) / period
        al = (al * (period - 1) + ls[i]) / period
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

def normalize_frame(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        level1 = df.columns.get_level_values(1).unique().tolist()
        if symbol in level1:
            try:
                df = df.xs(symbol, level=1, axis=1)
                if isinstance(df, pd.Series):
                    df = df.to_frame()
            except Exception:
                pass
        elif len(level1) == 1:
            df = df.droplevel(1, axis=1)
        elif len(df.columns.get_level_values(0).unique()) == 1:
            df = df.droplevel(0, axis=1)
        else:
            return pd.DataFrame()
    cols = {c: c.lower() for c in df.columns}
    df = df.rename(columns=cols)
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(set(df.columns)):
        return pd.DataFrame()
    df = df[["open", "high", "low", "close", "volume"]] if "volume" in df.columns else df[["open", "high", "low", "close"]]
    df = df.dropna(subset=["close"])
    return df

def fetch_yf(symbol, period='60d', interval='1d'):
    try:
        df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False, threads=False)
        return normalize_frame(df, symbol)
    except Exception:
        return pd.DataFrame()

def conviction_score(rsi_val, atr_val, last, sma20, sma50, news_score, backtest_score, backtested=False):
    score = 0.0
    # RSI component
    if rsi_val < 20 or rsi_val > 80:
        score += 3.0
    elif rsi_val < 30 or rsi_val > 70:
        score += 2.0
    elif rsi_val < 40 or rsi_val > 60:
        score += 1.0
    # Trend component
    if sma20 and sma50 and last:
        if last > sma20 > sma50:
            score += 2.0
        elif last < sma20 < sma50:
            score += 2.0
    # ATR component
    if atr_val and last:
        atr_pct = (atr_val / last) * 100 if last else 0
        if atr_pct > 2.0:
            score += 1.5
        elif atr_pct > 1.0:
            score += 1.0
    # News component
    if news_score > 60:
        score += 1.5
    elif news_score < 40:
        score += 1.0
    # Backtest component
    if backtested:
        if backtest_score and backtest_score >= 80:
            score += 3.0
        elif backtest_score and backtest_score >= 60:
            score += 2.0
        elif backtest_score and backtest_score >= 40:
            score += 1.0
    return round(score, 2)

def verify_prices(viable_setups, max_check=20):
    """Re-fetch top candidates and flag stale prices."""
    if not viable_setups:
        return viable_setups
    stale_symbols = set()
    for rec in viable_setups[:max_check]:
        sym = rec['symbol']
        try:
            df = fetch_yf(sym, period='5d', interval='1d')
            if df.empty or len(df) < 2:
                stale_symbols.add(sym)
                continue
            last_bar_date = df.index[-1]
            last_bar_close = float(df['close'].iloc[-1])
            reported = rec.get('last')
            if reported is None:
                stale_symbols.add(sym)
                continue
            pct_diff = abs(last_bar_close - reported) / reported * 100 if reported else 100
            rec['verified_last'] = round(last_bar_close, 6)
            rec['verified_asof'] = str(last_bar_date)
            rec['price_delta_pct'] = round(pct_diff, 3)
            if pct_diff > 1.5:
                stale_symbols.add(sym)
        except Exception:
            stale_symbols.add(sym)
    if stale_symbols:
        viable_setups = [r for r in viable_setups if r['symbol'] not in stale_symbols]
        for r in viable_setups:
            if r['symbol'] in stale_symbols:
                r['viable'] = False
                r['reason'] = [x for x in r.get('reason', []) if x != 'STALE_PRICE'] + ['STALE_PRICE']
    return viable_setups

# Main scan
results = {
    'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'universe_size': len(UNIVERSE),
    'sectors': {},
    'viable_setups': [],
}

for symbol, sector in UNIVERSE.items():
    brokers = SECTOR_BROKER.get(sector, ['IBKR', 'ALPACA', 'CAPITAL_RIGHT'])
    df = fetch_yf(symbol, period='60d', interval='1d')
    if df.empty or len(df) < 20:
        results['sectors'][symbol] = {
            'sector': sector, 'broker_routing': brokers, 'status': 'NO_DATA'
        }
        continue

    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    r = rsi(closes)
    a = atr(highs, lows, closes)
    sma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
    sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
    last = float(closes[-1])
    news_sent, news_sc, news_heads = news_for(symbol, sector)
    cb = CONVICTION_DB.get(symbol, {})
    bt_score = cb.get('backtest_score')
    bt_grade = cb.get('grade')
    bt_backtested = cb.get('backtested', False)
    conv = conviction_score(r, a, last, sma20, sma50, news_sc, bt_score, bt_backtested)

    # Viability: RSI extreme or strong trend
    viable = False
    reason = []
    if r < 30:
        viable = True
        reason.append('RSI_OVERSOLD')
    elif r > 70:
        viable = True
        reason.append('RSI_OVERBOUGHT')
    if sma20 and sma50 and last:
        if last > sma20 > sma50:
            viable = True
            reason.append('BULL_TREND')
        elif last < sma20 < sma50:
            viable = True
            reason.append('BEAR_TREND')
    if a is None or a == 0:
        viable = False
        reason = [r for r in reason if r not in ('RSI_OVERSOLD', 'RSI_OVERBOUGHT')]

    rec = {
        'symbol': symbol,
        'sector': sector,
        'broker_routing': brokers,
        'last': round(last, 6),
        'rsi': round(r, 2),
        'atr': round(a, 6) if a is not None else None,
        'sma20': round(sma20, 6) if sma20 else None,
        'sma50': round(sma50, 6) if sma50 else None,
        'news_sentiment': news_sent,
        'news_score': news_sc,
        'news_headlines': news_heads,
        'backtest_grade': bt_grade,
        'backtest_score': bt_score,
        'backtested': bt_backtested,
        'conviction': conv,
        'viable': viable,
        'reason': reason,
    }
    results['sectors'][symbol] = rec
    if viable:
        results['viable_setups'].append(rec)

# Sort viable by conviction desc
results['viable_setups'] = sorted(results['viable_setups'], key=lambda x: x['conviction'], reverse=True)
results['viable_setups'] = verify_prices(results['viable_setups'])
results['viable_count'] = len(results['viable_setups'])
results['scanned_count'] = len([k for k, v in results['sectors'].items() if v.get('status') != 'NO_DATA'])

OUT.write_text(json.dumps(results, indent=2), encoding='utf-8')
print('WROTE', OUT)
print('SCANNED', results['scanned_count'], 'VIABLE', results['viable_count'])
print('All sectors:', sorted(set(v['sector'] for v in results['sectors'].values() if isinstance(v, dict) and v.get('sector'))))
print('\nTop 20 setups:')
for x in results['viable_setups'][:20]:
    print(f"{x['symbol']:12} {x['sector']:18} conv={x['conviction']:4} rsi={x['rsi']:6} atr={x['atr']} news={x['news_sentiment']} bt={x['backtest_grade']}/{x['backtest_score']} backtested={x['backtested']} brokers={x['broker_routing']}")
