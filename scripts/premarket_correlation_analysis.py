#!/usr/bin/env python3
"""
Premarket Correlation Analysis — runs after premarket scan at 08:30 ET.
Loads scan setups, maps to correlated assets, explains directional impact.
"""
import json, sys, datetime
from pathlib import Path

BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
OUT_DIR = BASE_FIRM / 'workflow'

# Canonical correlation matrix from historical returns
CORR_PATH = OUT_DIR / 'correlation_matrix_20260812.json'

# Known directional relationships (from matrix + market knowledge)
GOLD_RELATIONS = {
    'DXY': 'NEGATIVE',
    'US10Y': 'NEGATIVE',
    'SPY': 'POSITIVE',
    'QQQ': 'POSITIVE',
    'XAGUSD': 'POSITIVE',
    'EURUSD': 'POSITIVE',
    'GBPUSD': 'POSITIVE',
    'AUDUSD': 'POSITIVE',
    'BTC-USD': 'POSITIVE',
    'ETH-USD': 'POSITIVE',
    'CL=F': 'NEGATIVE',
    'BZ=F': 'NEGATIVE',
}

SILVER_RELATIONS = {
    'DXY': 'NEGATIVE',
    'XAUUSD': 'POSITIVE',
    'SPY': 'POSITIVE',
    'QQQ': 'POSITIVE',
    'CL=F': 'NEGATIVE',
    'BZ=F': 'NEGATIVE',
    'EURUSD': 'POSITIVE',
    'GBPUSD': 'POSITIVE',
}

OIL_RELATIONS = {
    'DXY': 'POSITIVE',
    'US10Y': 'POSITIVE',
    'SPY': 'NEGATIVE',
    'QQQ': 'NEGATIVE',
    'XAUUSD': 'NEGATIVE',
    'XAGUSD': 'NEGATIVE',
    'CL=F': 'POSITIVE',
    'BZ=F': 'POSITIVE',
}

FX_RELATIONS = {
    'EURUSD': {'DXY': 'NEGATIVE', 'EURJPY': 'POSITIVE', 'GBPUSD': 'POSITIVE'},
    'GBPUSD': {'DXY': 'NEGATIVE', 'EURUSD': 'POSITIVE', 'GBPJPY': 'POSITIVE'},
    'USDJPY': {'DXY': 'POSITIVE', 'US10Y': 'POSITIVE', 'SPY': 'POSITIVE'},
    'AUDUSD': {'DXY': 'NEGATIVE', 'SPY': 'POSITIVE', 'XAUUSD': 'POSITIVE'},
    'NZDUSD': {'DXY': 'NEGATIVE', 'AUDUSD': 'POSITIVE', 'SPY': 'POSITIVE'},
    'USDCAD': {'DXY': 'POSITIVE', 'CL=F': 'POSITIVE', 'BZ=F': 'POSITIVE'},
}

CRYPTO_RELATIONS = {
    'BTC-USD': {'ETH-USD': 'POSITIVE', 'XRP-USD': 'POSITIVE', 'SPY': 'POSITIVE', 'QQQ': 'POSITIVE'},
    'ETH-USD': {'BTC-USD': 'POSITIVE', 'XRP-USD': 'POSITIVE', 'SPY': 'POSITIVE'},
    'XRP-USD': {'BTC-USD': 'POSITIVE', 'ETH-USD': 'POSITIVE', 'XRP-USD': 'POSITIVE'},
}

INDEX_RELATIONS = {
    'SPY': {'QQQ': 'POSITIVE', 'DXY': 'NEGATIVE', 'US10Y': 'NEGATIVE', 'BTC-USD': 'POSITIVE'},
    'QQQ': {'SPY': 'POSITIVE', 'DXY': 'NEGATIVE', 'US10Y': 'NEGATIVE', 'BTC-USD': 'POSITIVE'},
}

def load_latest_scan():
    scans = sorted(OUT_DIR.glob('nightshift_scan_*.json'))
    if not scans:
        return None
    return json.loads(scans[-1].read_text())

def load_corr_matrix():
    if CORR_PATH.exists():
        return json.loads(CORR_PATH.read_text())
    return {}

def normalize_symbol(sym):
    s = str(sym).upper()
    if '-' in s and s.endswith('USD'):
        s = s.replace('-USD', '')
    if s.startswith('^'):
        s = s[1:]
    if s.endswith('=F'):
        s = s[:-2]
    if s.endswith('=X'):
        s = s[:-2]
    return s

def map_to_corr_ticker(sym):
    """Map scan symbol to correlation matrix ticker."""
    s = normalize_symbol(sym)
    # Direct mappings
    if s in ('XAUUSD', 'GC=F'):
        return 'GC=F'
    if s in ('XAGUSD', 'SI=F'):
        return 'SI=F'
    if s in ('WTI', 'CL=F', 'WTIOIL'):
        return 'CL=F'
    if s in ('BRENT', 'BZ=F'):
        return 'BZ=F'
    if s in ('COPPER', 'HG=F'):
        return 'HG=F'
    if s in ('BTC', 'BTCUSD', 'BTC-USD'):
        return 'BTC-USD'
    if s in ('ETH', 'ETHUSD', 'ETH-USD'):
        return 'ETH-USD'
    if s in ('XRP', 'XRPUSD', 'XRP-USD'):
        return 'XRP-USD'
    if s in ('SPX500', 'US500', 'SPY'):
        return 'SPY'
    if s in ('NASDAQ', 'US100', 'QQQ'):
        return 'QQQ'
    if s in ('DXY', 'DX-Y.NYB'):
        return 'DXY'
    if s in ('EURUSD', 'EURUSD=X'):
        return 'EURUSD=X'
    if s in ('GBPUSD', 'GBPUSD=X'):
        return 'GBPUSD=X'
    if s in ('AUDUSD', 'AUDUSD=X'):
        return 'AUDUSD=X'
    if s in ('NZDUSD', 'NZDUSD=X'):
        return 'NZDUSD=X'
    if s in ('USDJPY', 'USDJPY=X'):
        return 'USDJPY=X'
    if s in ('USDCAD', 'USDCAD=X'):
        return 'USDCAD=X'
    if s in ('USDCHF', 'USDCHF=X'):
        return 'USDCHF=X'
    if s == 'US10Y':
        return '^TNX'
    return None

def get_correlations(symbol, corr_matrix, threshold=0.3):
    """Get correlated assets above threshold."""
    s = map_to_corr_ticker(symbol)
    if not s or s not in corr_matrix.get('correlation_matrix', {}):
        return []
    
    correlations = []
    for other, corr in corr_matrix['correlation_matrix'][s].items():
        if other == s:
            continue
        if abs(corr) >= threshold:
            correlations.append((other, corr))
    return sorted(correlations, key=lambda x: abs(x[1]), reverse=True)

def explain_relation(symbol, correlated_symbol, direction, corr_value):
    """Explain what it means if correlated_symbol moves."""
    s_norm = normalize_symbol(symbol)
    c_norm = normalize_symbol(correlated_symbol)
    
    explanations = {
        'XAUUSD': {
            'DXY': f'If DXY strengthens, expect XAUUSD to weaken (historical negative correlation {corr_value:.2f}). Watch USD flows.',
            'SI=F': f'If silver rises, gold often follows (positive correlation {corr_value:.2f}). Silver strength confirms precious metals bullishness.',
            'CL=F': f'Oil and gold often inversely correlated ({corr_value:.2f}). Rising oil pressures gold via inflation/recession concerns.',
            'BZ=F': f'Brent strength typically pressures gold ({corr_value:.2f}). Energy inflation trade.',
            'HG=F': f'Copper/gold positive correlation ({corr_value:.2f}) suggests industrial demand supporting metals.',
            'BTC-USD': f'Crypto-gold correlation ({corr_value:.2f}) is weak; crypto risk-on flows don\'t reliably drive gold.',
            'ETH-USD': f'Ethereum and gold show mild positive correlation ({corr_value:.2f}); both can benefit from liquidity injections.',
            'SPY': f'SPX-gold correlation ({corr_value:.2f}) is moderate; equities up can pressure gold as risk-on.',
            'QQQ': f'Nasdaq-gold correlation ({corr_value:.2f}); tech strength often = gold softness.',
            'US10Y': f'Treasury yields vs gold ({corr_value:.2f}); rising yields typically negative for gold.',
            'EURUSD': f'EUR/USD strength often lifts gold ({corr_value:.2f}) via USD weakness channel.',
            'GBPUSD': f'GBP strength correlates with gold ({corr_value:.2f}); both benefit from USD weakness.',
            'AUDUSD': f'Aussie strength lifts gold ({corr_value:.2f}) — AUD is commodity proxy.',
            'USDJPY': f'JPY strength can correlate with gold ({corr_value:.2f}) via safe-haven flows.',
        },
        'XAGUSD': {
            'GC=F': f'Silver follows gold ({corr_value:.2f}); gold breakout confirms silver momentum.',
            'DXY': f'Dollar strength pressures silver ({corr_value:.2f}) like gold.',
            'CL=F': f'Oil-silver negative correlation ({corr_value:.2f}); energy prices matter for silver.',
            'SPY': f'Equity strength can lift silver ({corr_value:.2f}) — industrial demand channel.',
            'EURUSD': f'EUR strength lifts silver ({corr_value:.2f}) via USD weakness.',
        },
        'CL=F': {
            'DXY': f'Dollar strength correlates with oil ({corr_value:.2f}) — petrodollar effect.',
            'BZ=F': f'Brent-WTI correlation ({corr_value:.2f}); near perfect co-movement.',
            'XAUUSD': f'Oil-gold negative correlation ({corr_value:.2f}); oil spike = inflation fear = gold bid.',
            'SPY': f'SPX-oil negative correlation ({corr_value:.2f}); oil shock fears hit equities.',
            'US10Y': f'Yields and oil positively correlated ({corr_value:.2f}); inflation expectations.',
        },
        'EURUSD': {
            'DXY': f'Dollar strength directly pressures EUR/USD ({corr_value:.2f}). EUR up = USD down = gold up.',
            'GBPUSD': f'EUR/GBP co-movement ({corr_value:.2f}); EUR strength often pulls GBP.',
            'GBPJPY': f'EUR/JPY correlation ({corr_value:.2f}); EUR strength lifts JPY crosses.',
            'USDCHF': f'EUR/CHF correlation ({corr_value:.2f}); EUR strength lifts CHF.',
        },
        'GBPUSD': {
            'DXY': f'Dollar strength pressures GBP ({corr_value:.2f}). GBP up = USD down = metals bid.',
            'EURUSD': f'EUR/GBP positive correlation ({corr_value:.2f}); GBP follows EUR.',
            'GBPJPY': f'GBP/JPY correlation ({corr_value:.2f}); GBP strength lifts JPY crosses.',
        },
        'USDJPY': {
            'DXY': f'Dollar strength lifts USD/JPY ({corr_value:.2f}) — direct USD channel.',
            'SPY': f'S&P strength lifts USD/JPY ({corr_value:.2f}); risk-on = JPY weak.',
            'US10Y': f'Rising yields strengthen USD/JPY ({corr_value:.2f}); carry trade dynamics.',
        },
        'BTC-USD': {
            'ETH-USD': f'Ethereum follows Bitcoin ({corr_value:.2f}); BTC move sets crypto market tone.',
            'XRP-USD': f'Ripple follows BTC ({corr_value:.2f}); altcoins amplify BTC moves.',
            'SPY': f'Bitcoin-SPX correlation ({corr_value:.2f}); crypto risk-on channel.',
            'QQQ': f'Nasdaq-BTC correlation ({corr_value:.2f}); tech/crypto liquidity linkage.',
        },
    }
    
    key = normalize_symbol(symbol)
    if key in explanations:
        if correlated_symbol in explanations[key]:
            return explanations[key][correlated_symbol]
    
    return f'{symbol} and {correlated_symbol} correlation: {corr_value:.2f}. Watch co-movement for regime shifts.'

def analyze_scan_correlations(scan_data, corr_matrix):
    """Generate correlation report for scan setups."""
    setups = scan_data.get('viable_setups', [])[:20]
    symbols = list(dict.fromkeys([s['symbol'] for s in setups]))
    
    report = []
    report.append('# Premarket Correlation Analysis')
    report.append(f'Generated: {scan_data.get("generated_at", "unknown")}')
    report.append(f'Scan setups: {len(setups)}')
    report.append('')
    
    for sym in symbols[:15]:  # Top 15 symbols
        corrs = get_correlations(sym, corr_matrix)
        if not corrs:
            continue
        
        report.append(f'## {sym}')
        report.append(f'Scan conviction: {next((s["conviction"] for s in setups if s["symbol"] == sym), "N/A")}')
        report.append('')
        
        for other, corr in corrs[:5]:
            direction = 'POSITIVE' if corr > 0 else 'NEGATIVE'
            strength = 'STRONG' if abs(corr) > 0.6 else 'MODERATE' if abs(corr) > 0.4 else 'WEAK'
            explanation = explain_relation(sym, other, direction, corr)
            report.append(f'- **{other}**: {direction} {strength} ({corr:.2f})')
            report.append(f'  - {explanation}')
        report.append('')
    
    # Cross-asset summary
    report.append('## Cross-Asset Summary')
    report.append('')
    
    # Gold correlations
    xau_corrs = get_correlations('XAUUSD', corr_matrix)
    if xau_corrs:
        report.append('### XAUUSD Correlations')
        for other, corr in xau_corrs[:5]:
            report.append(f'- {other}: {corr:+.2f}')
        report.append('')
    
    # Silver correlations
    xag_corrs = get_correlations('XAGUSD', corr_matrix)
    if xag_corrs:
        report.append('### XAGUSD Correlations')
        for other, corr in xag_corrs[:5]:
            report.append(f'- {other}: {corr:+.2f}')
        report.append('')
    
    # Crypto correlations
    btc_corrs = get_correlations('BTC-USD', corr_matrix)
    if btc_corrs:
        report.append('### BTC-USD Correlations')
        for other, corr in btc_corrs[:5]:
            report.append(f'- {other}: {corr:+.2f}')
        report.append('')
    
    # FX correlations
    eur_corrs = get_correlations('EURUSD', corr_matrix)
    if eur_corrs:
        report.append('### EURUSD Correlations')
        for other, corr in eur_corrs[:5]:
            report.append(f'- {other}: {corr:+.2f}')
        report.append('')
    
    return '\n'.join(report)

def main():
    scan_data = load_latest_scan()
    if not scan_data:
        print('No scan data found. Run premarket scan first.')
        sys.exit(1)
    
    corr_matrix = load_corr_matrix()
    if not corr_matrix:
        print('No correlation matrix found. Generate correlation_matrix_*.json first.')
        sys.exit(1)
    
    report = analyze_scan_correlations(scan_data, corr_matrix)
    out_path = OUT_DIR / f'premarket_correlation_{datetime.datetime.now().strftime("%Y%m%d%H%M")}.md'
    out_path.write_text(report, encoding='utf-8')
    print(f'Correlation report saved: {out_path}')
    print('\n' + report)

if __name__ == '__main__':
    main()
