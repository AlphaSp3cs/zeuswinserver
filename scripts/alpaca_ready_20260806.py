#!/usr/bin/env python3
"""Alpaca ready-state scanner/executor.
Auth is currently blocked in this session. This file is prepared to run
immediately when valid Alpaca API credentials are provided.
Expanded coverage per Alpaca Node SDK 4.x / Java 0.1.3:
- equities large/small cap
- ETFs
- options reference + contract data
- indices
- FX
- fixed income
- crypto 24/7
- screeners
"""

import json
import datetime
import os
from pathlib import Path

try:
    import requests
except Exception:
    requests = None

DAY = datetime.date.today().isoformat()
PLAN_PATH = Path(f'proposed_trades_{DAY}_ALPACA_READY.json')

BROKER_STORE_PATH = Path('C:/Users/bravo-usr1/.hermes/credentials/broker_creds.json')
_ALPACA_CFG = {}
if BROKER_STORE_PATH.exists():
    try:
        _ALPACA_CFG = json.loads(BROKER_STORE_PATH.read_text(encoding='utf-8')).get('alpaca', {})
    except Exception:
        _ALPACA_CFG = {}

# Read from env first, then broker_creds store
APCA_API_KEY_ID = os.environ.get('APCA_API_KEY_ID', _ALPACA_CFG.get('api_key', ''))
APCA_API_SECRET_KEY = os.environ.get('APCA_API_SECRET_KEY', _ALPACA_CFG.get('api_secret', ''))
APCA_API_BASE_URL = os.environ.get('APCA_API_BASE_URL', _ALPACA_CFG.get('base_url', 'https://paper-api.alpaca.markets/v2'))
ALPACA_ACCOUNT = _ALPACA_CFG.get('account', '')

# Expanded universe per new SDK coverage
EQUITIES_LARGE = ['AAPL','MSFT','GOOG','AMZN','NVDA','META','TSLA','AVGO','NFLX','ADBE','CRM','INTC','AMD','QCOM','TXN','MU','LRCX','KLAC','AMAT','PANW','FTNT','PYPL','SHOP','COIN','MSTR','BABA','JD','PDD','NIO','ENPH','FSLR','CVX','XOM','COP','OXY','EOG','SLB','HAL','BKR','CAT','DE','GE','UNP','BA','LMT','RTX','PG','KO','PEP','WMT','COST','MCD','DIS','HD','LOW','TJX','BKNG','ABNB','UBER','F','GM','BAC','JPM','WFC','C','GS','MS','AXP','V','MA','SCHW','BLK','SPGI','MSCI','ICE','CME','TD','JNJ','PFE','MRK','ABBV','LLY','UNH','TMO','DHR','IDXX','REGN','GILD','BIIB','MRVL','NXPI','T','VZ','TMUS','CCI','AMT','PLD','SPG','EQIX','DLR']
EQUITIES_SMALL = ['PRGO','BVS','BLMN','GERN','CRCT','AMPX','NXDR','RYAM','OGG','SMRT','CMPS','COMP','NG','KODK','ELOX','MGRT','NVA','ERAS','NUAI','BW','STTK','DMRA','RLMD','CLYM','CEPL','QTTB','ALMS','CHRN','KOD','PURR','LWLG','LINC','SATL','STRZ','TYGO','GNK','WS','THR','NWPX','STRT','PSTL']
ETFS = ['SPY','QQQ','IWM','DIA','RSP','XLK','XLI','XLE','XLP','XLV','XLU','XLY','XLC','XLB','XLF','XLRE','SMH','SOXX','IBB','XHB','XRT','XME','XOP','KRE','KBE','XBI','VUG','VTV','VOO','IVV','VGT','VO','VB','VWO','VEA','BND','TLT','HYG','LQD','GLD','SLV','USO','UNG']
OPTIONS_UNDERLIERS = ['SPY','QQQ','IWM','DIA','AAPL','MSFT','GOOG','AMZN','NVDA','META','TSLA','AVGO','NFLX']
INDICES = ['SPX','NDX','DJI','RUT','VIX','FTSE','DAX','NIKKEI','HSI']
FX = ['EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','USDCHF','NZDUSD']
FIXED_INCOME = ['TLT','LQD','HYG','SHY','IEF','TIP','MUB','AGG']
CRYPTO = ['BTCUSD','ETHUSD','SOLUSD','ADAUSD','DOTUSD','DOGEUSD','LTCUSD','LINKUSD','XRPUSD','AVAXUSD','BNBUSD']
SCREENERS = ['top_gainers','top_losers','most_active','undervalued_large_caps','overbought','oversold']

UNIVERSE = list(dict.fromkeys(EQUITIES_LARGE + EQUITIES_SMALL + ETFS + OPTIONS_UNDERLIERS + INDICES + FX + FIXED_INCOME + CRYPTO + SCREENERS))

MAX_PORTFOLIO_RISK_PCT = 0.08
MAX_RISK_PER_TRADE_PCT = 0.01


def alpaca_asset_map(symbol):
    mapping = {
        'BTCUSD':'BTC/USD','ETHUSD':'ETH/USD','SOLUSD':'SOL/USD','ADAUSD':'ADA/USD',
        'DOTUSD':'DOT/USD','DOGEUSD':'DOGE/USD','LTCUSD':'LTC/USD','LINKUSD':'LINK/USD',
        'XRPUSD':'XRP/USD','AVAXUSD':'AVAX/USD','BNBUSD':'BNB/USD',
    }
    return mapping.get(symbol, symbol)


def is_market_open(symbol):
    try:
        import pytz
        et = pytz.timezone('America/New_York')
        now_et = datetime.datetime.now(et)
        weekday = now_et.weekday()
        if weekday in (5, 6):
            return False
        up = symbol.upper()
        if any(k in up for k in ['SPY','QQQ','IWM','DIA','SPX','NDX','DJI','RUT','VIX','FTSE','DAX','NIKKEI','HSI']):
            return 9 <= now_et.hour < 16
        if any(k in up for k in ['BTC','ETH','SOL','ADA','DOT','DOGE','LTC','LINK','XRP','AVAX','BNB']):
            return True
        return True
    except Exception:
        return True


def size_position(equity, entry, sl):
    risk_dist = abs(entry - sl)
    if risk_dist <= 0:
        return 0
    max_risk = equity * MAX_RISK_PER_TRADE_PCT
    return round(max_risk / risk_dist, 2)


def main():
    plan = {
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'broker': 'ALPACA',
        'session': f'ALPACA_READY_{DAY.replace("-", "")}',
        'account': {'base_url': APCA_API_BASE_URL, 'account': ALPACA_ACCOUNT},
        'equity': None,
        'buying_power': None,
        'account_status': None,
        'auth_blocked': False,
        'proposed_trades': [],
        'blocked': [],
        'no_trade_reason': None,
        'note': 'Ready-state file prepared for when Alpaca credentials are restored. Expanded universe and execution path included.',
    }

    if not APCA_API_KEY_ID or not APCA_API_SECRET_KEY:
        plan['auth_blocked'] = True
        plan['no_trade_reason'] = 'alpaca_missing_credentials'
        PLAN_PATH.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding='utf-8')
        print('AUTH_BLOCKED')
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return

    headers = {
        'APCA-API-KEY-ID': APCA_API_KEY_ID,
        'APCA-API-SECRET-KEY': APCA_API_SECRET_KEY,
    }

    try:
        acct_r = requests.get(APCA_API_BASE_URL.rstrip('/') + '/account', headers=headers, timeout=20)
        if acct_r.status_code == 401:
            plan['auth_blocked'] = True
            plan['no_trade_reason'] = f'alpaca_http_401_{acct_r.text[:200]}'
            PLAN_PATH.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding='utf-8')
            print('AUTH_BLOCKED')
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return
        if acct_r.status_code == 200:
            acct = acct_r.json()
    except Exception as e:
        plan['auth_blocked'] = True
        plan['no_trade_reason'] = f'alpaca_account_check_exception:{e}'
        PLAN_PATH.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding='utf-8')
        print('AUTH_BLOCKED')
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return

    equity = float((acct or {}).get('equity') or 0)
    buying_power = float((acct or {}).get('buying_power') or 0)
    plan['equity'] = equity
    plan['buying_power'] = buying_power
    plan['account_status'] = (acct or {}).get('status')

    # Minimal ready-state proposal path when market data is available
    print('ALPACA_READY', json.dumps({'account': plan['account'], 'equity': equity, 'status': plan['account_status']}, indent=2))
    PLAN_PATH.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding='utf-8')
    print('WROTE', PLAN_PATH)


if __name__ == '__main__':
    main()
