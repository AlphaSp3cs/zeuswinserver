#!/usr/bin/env python3
"""
Direct nightshift universe scan across forex, commodities, indices, crypto.
Outputs workflow/nightshift_manual_scan_<timestamp>.json with viable setups.
"""
import json, datetime
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
OUT = BASE / 'workflow' / 'nightshift_manual_scan_20260816T2235Z.json'

UNIVERSE = {
    'indices': ['US30','US500','US100','JP225','UK100','HK50','EU50','AU200','DE40','ES35','FR40','IT40','SG30'],
    'crypto': [
        'BTCUSD','ETHUSD','SOLUSD','AVAXUSD','ADAUSD','XRPUSD','DOTUSD','LINKUSD','XMRUSD','ZECUSD','UNIUSD',
        'BCHUSD','EOSUSD','FILUSD','NEARUSD','ATOMUSD','ALGOUSD','VETUSD','THETAUSD','FTMUSD','SANDUSD','MANAUSD',
        'AXSUSD','IMXUSD','ARBUSD','OPUSD','MATICUSD','INJUSD','SUIUSD','SEIUSD','TIAUSD','APTUSD','MOVEUSD',
        'BLURUSD','PEPEUSD','WIFUSD','DOGEUSD','SHIBUSD','FLOKIUSD','FETUSD','RENDERUSD','GRTUSD','OCEANUSD',
        'AGIXUSD','LDOUSD','RPLUSD','SSVUSD','ENSUSD','BLZUSD','KAVAUSD','CRVUSD','SNXUSD','1INCHUSD',
        'USDTUSD','USDCUSD','DAIUSD'
    ],
    'forex': [
        'EURUSD','GBPUSD','USDJPY','AUDUSD','USDCHF','NZDUSD','USDCAD',
        'EURJPY','EURGBP','GBPJPY','AUDJPY','AUDNZD','AUDCAD','CADJPY','CHFJPY','NZDJPY',
        'EURCHF','EURCAD','EURAUD','GBPCHF','GBPAUD','GBPCAD','GBPNZD','NZDCHF','NZDCAD',
        'USDTRY','USDZAR','USDMXN','USDCNH','USDSGD','USDHKD','USDTHB','USDSEK','USDNOK','USDDKK','USDPLN'
    ],
    'commodities': [
        'XAUUSD','XAGUSD','XPTUSD','XPDUSD',
        'WTIOIL','BRENT','NGAS',
        'WHEAT','CORN','SOYBEAN','SUGAR','COFFEE','COCOA',
        'COPPER','LITHIUM','URANIUM'
    ],
}

YF_MAP = {
    'US30': '^DJI', 'US500': '^GSPC', 'US100': '^IXIC', 'JP225': '^N225', 'UK100': '^FTSE',
    'HK50': '^HSI', 'EU50': '^STOXX50E', 'AU200': '^AXJO', 'DE40': '^GDAXI', 'ES35': '^IBEX',
    'FR40': '^FCHI', 'IT40': '^STOXX50E', 'SG30': '^STI',
    'BTCUSD': 'BTC-USD', 'ETHUSD': 'ETH-USD', 'SOLUSD': 'SOL-USD', 'AVAXUSD': 'AVAX-USD',
    'ADAUSD': 'ADA-USD', 'XRPUSD': 'XRP-USD', 'DOTUSD': 'DOT-USD', 'LINKUSD': 'LINK-USD',
    'XMRUSD': 'XMR-USD', 'ZECUSD': 'ZEC-USD', 'UNIUSD': 'UNI-USD', 'BCHUSD': 'BCH-USD',
    'EOSUSD': 'EOS-USD', 'FILUSD': 'FIL-USD', 'NEARUSD': 'NEAR-USD', 'ATOMUSD': 'ATOM-USD',
    'ALGOUSD': 'ALGO-USD', 'VETUSD': 'VET-USD', 'THETAUSD': 'THETA-USD', 'FTMUSD': 'FTM-USD',
    'SANDUSD': 'SAND-USD', 'MANAUSD': 'MANA-USD', 'AXSUSD': 'AXS-USD', 'IMXUSD': 'IMX-USD',
    'ARBUSD': 'ARB-USD', 'OPUSD': 'OP-USD', 'MATICUSD': 'POL-USD', 'INJUSD': 'INJ-USD',
    'SUIUSD': 'SUI-USD', 'SEIUSD': 'SEI-USD', 'TIAUSD': 'TIA-USD', 'APTUSD': 'APT-USD',
    'MOVEUSD': 'MOVE-USD', 'BLURUSD': 'BLUR-USD', 'PEPEUSD': 'PEPE-USD', 'WIFUSD': 'WIF-USD',
    'DOGEUSD': 'DOGE-USD', 'SHIBUSD': 'SHIB-USD', 'FLOKIUSD': 'FLOKI-USD', 'FETUSD': 'FET-USD',
    'RENDERUSD': 'RENDER-USD', 'GRTUSD': 'GRT-USD', 'OCEANUSD': 'OCEAN-USD', 'AGIXUSD': 'AGIX-USD',
    'LDOUSD': 'LDO-USD', 'RPLUSD': 'RPL-USD', 'SSVUSD': 'SSV-USD', 'ENSUSD': 'ENS-USD',
    'BLZUSD': 'BLZ-USD', 'KAVAUSD': 'KAVA-USD', 'CRVUSD': 'CRV-USD', 'SNXUSD': 'SNX-USD',
    '1INCHUSD': '1INCH-USD', 'USDTUSD': 'USDT-USD', 'USDCUSD': 'USDC-USD', 'DAIUSD': 'DAI-USD',
    'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'USDJPY': 'USDJPY=X', 'AUDUSD': 'AUDUSD=X',
    'USDCHF': 'USDCHF=X', 'NZDUSD': 'NZDUSD=X', 'USDCAD': 'USDCAD=X',
    'EURJPY': 'EURJPY=X', 'EURGBP': 'EURGBP=X', 'GBPJPY': 'GBPJPY=X',
    'AUDJPY': 'AUDJPY=X', 'AUDNZD': 'AUDNZD=X', 'AUDCAD': 'AUDCAD=X', 'CADJPY': 'CADJPY=X',
    'CHFJPY': 'CHFJPY=X', 'NZDJPY': 'NZDJPY=X', 'EURCHF': 'EURCHF=X', 'EURCAD': 'EURCAD=X',
    'EURAUD': 'EURAUD=X', 'GBPCHF': 'GBPCHF=X', 'GBPAUD': 'GBPAUD=X', 'GBPCAD': 'GBPCAD=X',
    'GBPNZD': 'GBPNZD=X', 'NZDCHF': 'NZDCHF=X', 'NZDCAD': 'NZDCAD=X',
    'USDTRY': 'USDTRY=X', 'USDZAR': 'USDZAR=X', 'USDMXN': 'USDMXN=X', 'USDCNH': 'USDCNY=X',
    'USDSGD': 'USDSGD=X', 'USDHKD': 'USDHKD=X', 'USDTHB': 'USDTHB=X', 'USDSEK': 'USDSEK=X',
    'USDNOK': 'USDNOK=X', 'USDDKK': 'USDDKK=X', 'USDPLN': 'USDPLN=X',
    'XAUUSD': 'GC=F', 'XAGUSD': 'SI=F', 'XPTUSD': 'PL=F', 'XPDUSD': 'HG=F',
    'WTIOIL': 'CL=F', 'BRENT': 'BZ=F', 'NGAS': 'NG=F',
    'WHEAT': 'ZW=F', 'CORN': 'ZC=F', 'SOYBEAN': 'ZS=F', 'SUGAR': 'SB=F', 'COFFEE': 'KC=F', 'COCOA': 'CC=F',
    'COPPER': 'HG=F', 'LITHIUM': '', 'URANIUM': '',
}

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
        level0 = df.columns.get_level_values(0).unique().tolist()
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
        elif len(level0) == 1:
            df = df.droplevel(0, axis=1)
        else:
            try:
                df = df[symbol]
                if isinstance(df, pd.Series):
                    df = df.to_frame()
            except Exception:
                return pd.DataFrame()
    cols = {c: c.lower() for c in df.columns}
    df = df.rename(columns=cols)
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(set(df.columns)):
        return pd.DataFrame()
    df = df[["open", "high", "low", "close", "volume"]] if "volume" in df.columns else df[["open", "high", "low", "close"]]
    df = df.dropna(subset=["close"])
    return df

def fetch_yf(symbol, period='30d', interval='1d'):
    try:
        df = yf.download(symbol, period=period, interval=interval, auto_adjust=True, progress=False, threads=False)
        return normalize_frame(df, symbol)
    except Exception:
        return pd.DataFrame()

results = {'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'universe': {}}
for asset_class, symbols in UNIVERSE.items():
    class_results = []
    for sym in symbols:
        yf_sym = YF_MAP.get(sym, sym)
        if not yf_sym:
            continue
        df = fetch_yf(yf_sym, period='30d', interval='1d')
        if df.empty or len(df) < 20:
            continue
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        r = rsi(closes)
        a = atr(highs, lows, closes)
        sma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
        sma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
        last = float(closes[-1])
        viable = False
        reason = []
        if r < 30:
            viable = True
            reason.append('RSI_OVERSOLD')
        elif r > 70:
            viable = True
            reason.append('RSI_OVERBOUGHT')
        if sma20 and sma50:
            if last > sma20 > sma50:
                viable = True
                reason.append('BULL_TREND')
            elif last < sma20 < sma50:
                viable = True
                reason.append('BEAR_TREND')
        if a is None or a == 0:
            viable = False
        class_results.append({
            'symbol': sym,
            'yf_symbol': yf_sym,
            'asset_class': asset_class,
            'last': round(last, 6),
            'rsi': round(r, 2),
            'sma20': round(sma20, 6) if sma20 else None,
            'sma50': round(sma50, 6) if sma50 else None,
            'atr': round(a, 6) if a is not None else None,
            'viable': viable,
            'reason': reason,
        })
    results['universe'][asset_class] = {
        'scanned': len(class_results),
        'viable': sum(1 for x in class_results if x['viable']),
        'results': class_results,
    }

summary = {}
for ac, data in results['universe'].items():
    viable = [x for x in data['results'] if x['viable']]
    summary[ac] = {
        'scanned': data['scanned'],
        'viable_count': len(viable),
        'top': sorted(viable, key=lambda x: abs(x['rsi']-50), reverse=True)[:10],
    }

results['summary'] = summary
OUT.write_text(json.dumps(results, indent=2), encoding='utf-8')
print('WROTE', OUT)
for ac, s in summary.items():
    print(ac, s['scanned'], 'viable', s['viable_count'])
    for x in s['top'][:5]:
        print(' ', x['symbol'], x['last'], 'rsi', x['rsi'], x['reason'])
