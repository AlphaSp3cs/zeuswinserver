#!/usr/bin/env python3
"""
Weekend Crypto DCA Scanner
- Scans ALL crypto assets continuously
- Identifies buy setups even for assets NOT in portfolio
- Uses free APIs: CoinGecko + yfinance
- Applies institutional scorecard framework
- Generates Windows toasts + auto-tickets
"""
import json, time, sqlite3, re, sys, uuid
from pathlib import Path
from datetime import datetime, timezone

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False

# bravo: toasts OFF (Telegram-only law)
import os as _os_dg
if _os_dg.environ.get('OURO_DISABLE_TOAST','').strip().lower() in ('1','true','yes'):
    class _NoToast:
        def __getattr__(self,n): return lambda *a,**k: None
    Notification = _NoToast()
    def _disabled_audio(*a,**k): pass
    audio = type('A',(),{'Default':staticmethod(_disabled_audio),'Reminder':staticmethod(_disabled_audio)})()

try:
    import yfinance as yf
    HAS_YF = True
except ImportError:
    HAS_YF = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

BASE_DESKTOP = Path(r'C:\Users\bravo-usr1\Desktop')
BASE_FIRM = BASE_DESKTOP / 'OuroTaurus Trade Firm'
DB_PATH = BASE_FIRM / 'workflow' / 'crypto_data.db'
ALERT_LOG = BASE_FIRM / 'dca_alerts_all_assets.jsonl'
TICKET_FILE = BASE_FIRM / 'workflow' / 'dca_execution_auto_tickets_20260808.md'
SCORE_TRACKER = BASE_FIRM / 'workflow' / 'scorecard_tracker.json'
BROKER_MATRIX = BASE_FIRM / 'workflow' / 'broker_routing_matrix.json'
UNIVERSE_FILE = BASE_FIRM / 'workflow' / 'crypto_universe_20260809.json'
WHALE_FILE = BASE_FIRM / 'workflow' / 'whale_investor_tracker.json'
EQUITY_WATCHLIST_FILE = BASE_DESKTOP / 'dividend_dca_watchlist_20260808.md'

# Clarity Act 1 eligible + major crypto assets
_CRYPTO_UNIVERSE = [
    'BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'AVAX', 'DOT', 'INJ', 'LTC', 'LINK',
    'TAO', 'AAVE', 'UNI', 'ARB', 'NEAR', 'HYPE', 'SUI', 'APT', 'OP', 'MATIC',
    'FTM', 'ALGO', 'ATOM', 'OSMO', 'DYDX', 'LDO', 'RPL', 'ENS', 'BLUR', 'COMP',
    'MKR', 'SNX', 'CRV', '1INCH', 'ZRX', 'KNC', 'REN', 'BAL', 'SUSHI', 'YFI',
    'ADA', 'XLM', 'ICP', 'PEPE', 'TRUMP', 'FET', 'CRO', 'ESP', 'MMT'
]

_COINGECKO_ID_MAP = {
    'ADA': 'cardano',
    'XLM': 'stellar',
    'LINK': 'chainlink',
    'DOT': 'polkadot',
    'INJ': 'injective',
    'LTC': 'litecoin',
    'AVAX': 'avalanche',
    'AAVE': 'aave',
    'UNI': 'uniswap',
    'ARB': 'arbitrum',
    'NEAR': 'near',
    'SUI': 'sui',
    'APT': 'aptos',
    'MATIC': 'matic-polygon',
    'FTM': 'fantom',
    'ALGO': 'algorand',
    'ATOM': 'cosmos',
    'DYDX': 'dydx',
    'LDO': 'lido-dao',
    'RPL': 'rocket-pool',
    'ENS': 'ethereum-name-service',
    'BLUR': 'blur',
    'COMP': 'compound-governance-token',
    'MKR': 'maker',
    'SNX': 'havven',
    'CRV': 'curve-dao-token',
    '1INCH': '1inch',
    'ZRX': '0x',
    'KNC': 'kyber-network',
    'REN': 'ren',
    'BAL': 'balancer',
    'SUSHI': 'sushi',
    'YFI': 'yearn-finance',
    'HYPE': 'hyperliquid',
    'OP': 'optimism',
    'OSMO': 'osmosis',
    'ICP': 'internet-computer',
    'PEPE': 'pepe',
    'TRUMP': 'trump',
    'FET': 'fetch-ai',
    'CRO': 'cronos',
    'ESP': 'esports',
    'MMT': 'mm-token',
}

if UNIVERSE_FILE.exists():
    try:
        _u = json.loads(UNIVERSE_FILE.read_text(encoding='utf-8'))
        CRYPTO_UNIVERSE = _u.get('symbols', _CRYPTO_UNIVERSE)
        COINGECKO_ID_MAP = {**_u.get('coingecko_ids', {}), **_COINGECKO_ID_MAP}
    except Exception:
        CRYPTO_UNIVERSE = _CRYPTO_UNIVERSE
        COINGECKO_ID_MAP = _COINGECKO_ID_MAP
else:
    CRYPTO_UNIVERSE = _CRYPTO_UNIVERSE
    COINGECKO_ID_MAP = _COINGECKO_ID_MAP

BUY_SETUP_TRIGGERS = {
    'rsi_oversold': 35,
    'price_drop_24h_pct': -10.0,
    'price_drop_7d_pct': -20.0,
    'volume_spike_mult': 2.5,
    'funding_rate_negative': True,
    'score_upgrade_min': 1,
}
SHORT_SETUP_TRIGGERS = {
    'rsi_overbought': 65,
    'price_rise_24h_pct': 10.0,
    'price_rise_7d_pct': 20.0,
    'volume_spike_mult': 2.5,
}
BROKER_SHORT_CAPABLE = {'KRAKEN', 'FTMO_LEFT', 'ALPACA', 'ETORO'}
MAX_POSITION_USD = 100.0  # hard cap per ticket unless explicitly overridden by broker risk rules

BROKER_ROUTING_CRYPTO = ['KRAKEN', 'FTMO_LEFT', 'CAPITAL_RIGHT', 'ALPACA', 'ETORO']
MT5_TERMINALS = {
    'FTMO_LEFT': r'REDACTED-PATH',
    'CAPITAL_RIGHT': r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe',
}

# eToro demo routing
ETORO_DEMO = True
ETORO_SYMBOL_MAP = BASE_FIRM / 'workflow' / 'etoro_symbol_map.json'
ETORO_TRADE_LOG = BASE_FIRM / 'workflow' / 'etoro_demo_trades.jsonl'
ETORO_BASE = 'https://public-api.etoro.com'
ETORO_API_KEY = 'sdgdskldFPLGfjHn1421dgnlxdGTbngdflg6290bRjslfihsjhSDsdgGHH25hjf'
ETORO_USER_KEY = 'eyJjaSI6IjYwY2FiYjBiLTU1OTctNDQ4NS04ZjYzLTdlOWUwNTZlMGJiOCIsImVhbiI6IlVucmVnaXN0ZXJlZEFwcGxpY2F0aW9uIiwiZWsiOiIuVjZ3S2xJOEpTajlrbHRySndMeHMzNEMwMXkuMDFrNG8tWjBScGllYzBCUHBSc1JrR3JocUQ3RHh2Q01wY3QtRURQSlFMTE1UalJiQ0VBNkxUYklhSklULnJkVnFGYjdGcjJSYjZpakhnUV8ifQ__'


class WeekendCryptoScanner:
    def __init__(self):
        self.conn = sqlite3.connect(str(DB_PATH))
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._ensure_tables()
        self.score_tracker = self._load_json(SCORE_TRACKER)
        self.broker_matrix = self._load_json(BROKER_MATRIX)
        self.alerts_this_cycle = []
        self.tickets_this_cycle = []
        self.CRYPTO_UNIVERSE = list(CRYPTO_UNIVERSE)

    def _load_json(self, path):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                pass
        return {}

    def _save_json(self, path, data):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')

    def _ensure_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS crypto_scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                price_usd REAL,
                change_24h_pct REAL,
                change_7d_pct REAL,
                rsi_14 REAL,
                volume_24h REAL,
                volume_7d_avg REAL,
                funding_rate REAL,
                market_cap REAL,
                score_grade TEXT,
                buy_setup BOOLEAN,
                signal_type TEXT,
                urgency TEXT,
                timestamp TEXT
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                symbol TEXT,
                broker TEXT,
                detail TEXT,
                timestamp TEXT
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS dca_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT,
                symbol TEXT,
                asset_type TEXT,
                broker TEXT,
                direction TEXT,
                order_type TEXT,
                entry REAL,
                sl REAL,
                tp1 REAL,
                tp2 REAL,
                size REAL,
                grade TEXT,
                score REAL,
                urgency TEXT,
                status TEXT DEFAULT 'READY',
                mt5_terminal TEXT,
                created_at TEXT,
                filled_at TEXT,
                fill_price REAL,
                pnl_usd REAL
            )
        ''')
        # Local low-risk migration: recreate with new columns if missing
        try:
            cols = [r[1] for r in self.cursor.execute('PRAGMA table_info(dca_tickets)').fetchall()]
            if 'grade' not in cols or 'score' not in cols:
                self.cursor.execute('ALTER TABLE dca_tickets RENAME TO dca_tickets_old')
                self.cursor.execute('''
                    CREATE TABLE dca_tickets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_id TEXT,
                        symbol TEXT,
                        asset_type TEXT,
                        broker TEXT,
                        direction TEXT,
                        order_type TEXT,
                        entry REAL,
                        sl REAL,
                        tp1 REAL,
                        tp2 REAL,
                        size REAL,
                        grade TEXT,
                        score REAL,
                        urgency TEXT,
                        status TEXT DEFAULT 'READY',
                        mt5_terminal TEXT,
                        created_at TEXT,
                        filled_at TEXT,
                        fill_price REAL,
                        pnl_usd REAL
                    )
                ''')
                self.cursor.execute('INSERT INTO dca_tickets SELECT id, ticket_id, symbol, asset_type, broker, direction, order_type, entry, sl, tp1, tp2, size, NULL, NULL, urgency, status, mt5_terminal, created_at, filled_at, fill_price, pnl_usd FROM dca_tickets_old')
                self.cursor.execute('DROP TABLE dca_tickets_old')
                self.conn.commit()
        except Exception:
            pass
        self.conn.commit()

    def _coingecko_simple(self):
        if not HAS_REQUESTS:
            return {}
        try:
            data = {}
            symbols = self.CRYPTO_UNIVERSE[:120]
            chunks = [symbols[i:i+4] for i in range(0, len(symbols), 4)]
            for chunk in chunks:
                cids = ','.join([COINGECKO_ID_MAP.get(s, s.lower()) for s in chunk])
                curl = f'https://api.coingecko.com/api/v3/simple/price?ids={cids}&vs_currencies=usd&include_24hr_change=true&include_market_cap=true'
                for attempt in range(3):
                    try:
                        resp = requests.get(curl, timeout=15)
                        if resp.status_code == 200:
                            data.update(resp.json())
                            break
                        elif resp.status_code == 429:
                            time.sleep(2 * (attempt + 1))
                        else:
                            break
                    except Exception:
                        time.sleep(1)
                time.sleep(0.5)
            return data
        except Exception:
            pass
        return {}

    def _coingecko_market_chart(self, symbol, days=7):
        if not HAS_REQUESTS:
            return [], []
        try:
            cid = COINGECKO_ID_MAP.get(symbol, symbol.lower())
            url = f'https://api.coingecko.com/api/v3/coins/{cid}/market_chart?vs_currency=usd&days={days}'
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('prices', []), data.get('total_volumes', [])
            elif resp.status_code == 429:
                time.sleep(3)
        except Exception:
            pass
        return [], []

    def _calc_rsi(self, prices, period=14):
        if not prices or len(prices) < period + 1:
            return None
        closes = [p[1] if isinstance(p, (list, tuple)) else p for p in prices]
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            return 70.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _yf_crypto_data(self, symbol):
        if not HAS_YF:
            return None
        try:
            return self._yf_crypto_data_inner(symbol)
        except Exception:
            return None

    def _yf_crypto_data_inner(self, symbol):
        ticker = yf.Ticker(f"{symbol}-USD")
        hist = ticker.history(period="3mo", interval="1d")
        if hist is None or hist.empty:
            return None
        closes = hist['Close'].tolist()
        if len(closes) < 15:
            return None
        current = float(closes[-1])
        prev = next((float(c) for c in reversed(closes[:-1]) if c and float(c) > 0), current)
        change_24h = ((current - prev) / prev * 100) if prev else 0
        week_idx = -1
        for i in range(len(closes) - 1, max(len(closes) - 10, -1), -1):
            if closes[i]:
                week_idx = i
                break
        change_7d = ((current - float(closes[week_idx])) / float(closes[week_idx]) * 100) if week_idx and week_idx >= 0 and float(closes[week_idx]) else 0
        volumes = [v for v in hist['Volume'].tolist() if isinstance(v, (int, float))]
        avg_vol_7d = sum(volumes[-7:]) / 7 if len(volumes) >= 7 else (sum(volumes) / max(1, len(volumes)) if volumes else 0)
        current_vol = volumes[-1] if volumes else 0
        rsi = self._calc_rsi(closes)
        return {
            'price': current,
            'change_24h_pct': change_24h,
            'change_7d_pct': change_7d,
            'volume_24h': current_vol,
            'volume_7d_avg': avg_vol_7d,
            'rsi_14': rsi,
        }

    def _batch_yf_crypto_data(self, symbols):
        """Batch-fetch yfinance data for many symbols at once."""
        if not HAS_YF or not symbols:
            return {}
        tickers = [f"{s}-USD" for s in symbols]
        results = {}
        try:
            data = yf.download(tickers=" ".join(tickers), period="3mo", interval="1d", threads=True, progress=False)
            if data is None or data.empty:
                return {}
            for sym, yf_ticker in zip(symbols, tickers):
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if len(data.columns.levels) > 1 and yf_ticker in data.columns.get_level_values(1):
                            sub = data[yf_ticker]
                        elif 'Close' in data.columns:
                            sub = data
                        else:
                            continue
                    else:
                        sub = data if len(tickers) == 1 else None
                    if sub is None or sub.empty:
                        continue
                    closes = sub['Close'].dropna().tolist()
                    if len(closes) < 15:
                        continue
                    current = float(closes[-1])
                    prev = next((float(c) for c in reversed(closes[:-1]) if c and float(c) > 0), current)
                    change_24h = ((current - prev) / prev * 100) if prev else 0
                    week_idx = -1
                    for i in range(len(closes) - 1, max(len(closes) - 10, -1), -1):
                        if closes[i]:
                            week_idx = i
                            break
                    change_7d = ((current - float(closes[week_idx])) / float(closes[week_idx]) * 100) if week_idx and week_idx >= 0 and float(closes[week_idx]) else 0
                    volumes = [v for v in sub['Volume'].dropna().tolist() if isinstance(v, (int, float))]
                    avg_vol_7d = sum(volumes[-7:]) / 7 if len(volumes) >= 7 else (sum(volumes) / max(1, len(volumes)) if volumes else 0)
                    current_vol = volumes[-1] if volumes else 0
                    rsi = self._calc_rsi(closes)
                    results[sym] = {
                        'price': current,
                        'change_24h_pct': change_24h,
                        'change_7d_pct': change_7d,
                        'volume_24h': current_vol,
                        'volume_7d_avg': avg_vol_7d,
                        'rsi_14': rsi,
                    }
                except Exception:
                    continue
        except Exception:
            return {}
        return results

    def _score_crypto(self, symbol, cg_data, yf_data):
        score = 0
        reasons = []
        price = yf_data['price'] if yf_data else cg_data.get('usd', 0)
        change_24h = yf_data['change_24h_pct'] if yf_data else (cg_data.get('usd_24h_change') or 0)
        change_7d = yf_data['change_7d_pct'] if yf_data else 0
        rsi = yf_data['rsi_14'] if yf_data else 50
        vol_ratio = (yf_data['volume_24h'] / yf_data['volume_7d_avg']) if yf_data and yf_data.get('volume_7d_avg', 0) > 0 else 1

        # Check 1: 7d drop
        if change_7d <= -20:
            score += 1
            reasons.append('7d_drop_20pct')
        elif change_7d <= -10:
            score += 0.5
            reasons.append('7d_drop_10pct')

        # Check 2: RSI
        rsi_val = rsi if rsi is not None else 50
        if rsi_val < 30:
            score += 1
            reasons.append('rsi_oversold')
        elif rsi_val < 35:
            score += 0.5
            reasons.append('rsi_near_oversold')

        # Check 3: 24h drop
        if change_24h <= -10:
            score += 1
            reasons.append('24h_drop_10pct')
        elif change_24h <= -5:
            score += 0.5
            reasons.append('24h_drop_5pct')

        # Check 4: Volume spike
        if vol_ratio >= 2.5:
            score += 1
            reasons.append('volume_spike')
        elif vol_ratio >= 1.8:
            score += 0.5
            reasons.append('volume_elevated')

        # Check 5: yfinance analyst/sentiment proxy removed for cycle speed
        # Grade remains based on price/volume/RSI only

        grade = 'ACCUMULATE' if score >= 4 else 'MIXED' if score >= 2 else 'AVOID'
        return {
            'score': score,
            'grade': grade,
            'reasons': reasons,
            'symbol': '',
            'price_usd': price,
            'change_24h_pct': change_24h,
            'change_7d_pct': change_7d,
            'rsi_14': rsi,
            'volume_24h': 0,
            'volume_7d_avg': 0,
            'volume_ratio': vol_ratio,
            'funding_rate': 0,
            'market_cap': cg_data.get('usd_market_cap', 0) or 0,
            'timestamp': '',
        }

    def _sector_for_symbol(self, symbol):
        mapping = {
            'BTC': 'Store_of_Value', 'ETH': 'Smart_Contract_Platform',
            'SOL': 'L1_Core', 'XRP': 'Payments', 'ADA': 'L1_Core',
            'AVAX': 'L1_Core', 'DOT': 'L1_Core', 'INJ': 'DeFi_Infrastructure',
            'NEAR': 'L1_Core', 'APT': 'L1_Core', 'SUI': 'L1_Core',
            'OP': 'L2_Scaling', 'MATIC': 'L2_Scaling', 'FTM': 'L1_Core',
            'ALGO': 'L1_Core', 'ATOM': 'L1_Core', 'OSMO': 'L1_Core',
            'DYDX': 'DeFi_Derivatives', 'LDO': 'DeFi_Infrastructure', 'RPL': 'DeFi_Infrastructure',
            'ARB': 'L2_Scaling', 'IMX': 'Gaming_Infrastructure', 'METIS': 'L2_Scaling',
            'CFX': 'L1_Core', 'ZKS': 'L2_Scaling', 'STX': 'BTC_L2', 'TIA': 'Modular',
            'AAVE': 'DeFi_Lending', 'UNI': 'DEX', 'LINK': 'Oracle',
            'COMP': 'DeFi_Lending', 'MKR': 'DeFi_Stablecoins', 'SNX': 'DeFi_Derivatives',
            'CRV': 'DEX', '1INCH': 'DEX_Aggregator', 'ZRX': 'DEX_Infrastructure',
            'KNC': 'DEX_Aggregator', 'BAL': 'DEX', 'SUSHI': 'DEX', 'YFI': 'DeFi_Yield',
            'REN': 'DeFi_Infrastructure', 'ENS': 'Web3_Identity', 'BLUR': 'NFT_Infrastructure',
            'TAO': 'AI_Compute', 'FET': 'AI_Compute', 'RNDR': 'AI_Compute',
            'AGIX': 'AI_Compute', 'OCEAN': 'AI_Data', 'ARKM': 'AI_Data',
            'WLD': 'AI_Identity', 'SAND': 'Gaming', 'MANA': 'Gaming',
            'AXS': 'Gaming', 'GALA': 'Gaming', 'FLOW': 'Gaming',
            'ENJ': 'Gaming_Infrastructure', 'CHZ': 'Sports_Crypto',
            'XMR': 'Privacy', 'ZEC': 'Privacy', 'DASH': 'Privacy', 'SCRT': 'Privacy_Contracts',
            'DOGE': 'Meme_Payments', 'SHIB': 'Meme_Ecosystem', 'PEPE': 'Meme',
            'WIF': 'Meme', 'BONK': 'Meme', 'FLOKI': 'Meme_Ecosystem',
            'TRUMP': 'Meme_Political', 'CRO': 'Exchange_Tokens',
            'BNB': 'Exchange_Tokens', 'OKB': 'Exchange_Tokens', 'KCS': 'Exchange_Tokens',
            'HTX': 'Exchange_Tokens', 'LEO': 'Exchange_Tokens',
            'FIL': 'Storage', 'AR': 'Storage', 'STORJ': 'Storage',
            'HNT': 'IoT', 'IOTX': 'IoT', 'POND': 'DeFi_Infrastructure',
            'ICP': 'DWeb', 'HOT': 'DWeb', 'VET': 'Supply_Chain',
            'API3': 'Oracle', 'BAND': 'Oracle',
            'USDT': 'Stablecoins', 'USDC': 'Stablecoins', 'DAI': 'Stablecoins',
            'FDUSD': 'Stablecoins', 'PYUSD': 'Stablecoins',
            'XLM': 'Payments', 'HYPE': 'DeFi_Derivatives', 'LTC': 'Payments',
        }
        return mapping.get(symbol, 'Other_Crypto')

    def _send_toast(self, title, msg, urgency='MEDIUM', duration='short'):
        if not HAS_WINOTIFY:
            return
        try:
            toast = Notification(app_id="Zeus Crypto Weekend Scan", title=title, msg=msg)
            if urgency == 'HIGH':
                toast.set_audio(audio.Mail, loop=False)
            else:
                toast.set_audio(audio.Default, loop=False)
            toast.show()
        except Exception:
            pass

    def _pick_broker(self, symbol):
        """Anticipate broker: prefer eToro if symbol is in eToro library, else fallback."""
        symbol_norm = symbol.replace('-USD', '').upper()
        try:
            symbol_map = json.loads(ETORO_SYMBOL_MAP.read_text(encoding='utf-8'))
            if symbol_norm in symbol_map or symbol in symbol_map:
                return 'ETORO'
        except Exception:
            pass
        return 'KRAKEN'

    def _send_trade_toast(self, sig, ticket):
        """Actionable trade toast with entry/SL/TP/size/broker."""
        if not HAS_WINOTIFY:
            return
        try:
            direction = sig.get('direction', 'LONG')
            title = f"WEEKEND CRYPTO {'SELL' if direction=='SHORT' else 'BUY'}: {sig['symbol']}"
            msg = (
                f"Broker: {sig.get('broker')} | Dir: {direction}\n"
                f"Entry: {sig.get('price'):.4f} | SL: {ticket.get('sl'):.4f} | TP1: {ticket.get('tp1'):.4f} | TP2: {ticket.get('tp2'):.4f}\n"
                f"Size: {ticket.get('size'):.4f} | Urgency: {sig.get('urgency')}\n"
                f"Reason: {sig.get('reason')}"
            )
            toast = Notification(app_id="Zeus Crypto Weekend Trade", title=title, msg=msg)
            toast.set_audio(audio.Mail, loop=False)
            toast.show()
        except Exception:
            pass

    def _bridge_to_etoro_demo(self, sig, ticket):
        """Enqueue toast signal for eToro demo execution."""
        try:
            import importlib.util, sys
            spec = importlib.util.spec_from_file_location('toast_to_etoro_demo', str(BASE_FIRM / 'scripts' / 'toast_to_etoro_demo.py'))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.enqueue_signal(sig, ticket)
        except Exception as e:
            print(f'[etoro-bridge] enqueue failed: {e}')

    def _send_cycle_summary(self, scan_count, buy_signals, sell_signals, tickets):
        """Cycle summary toast with actionable trade count."""
        if not HAS_WINOTIFY:
            return
        try:
            title = f"Weekend Crypto Scan: {scan_count} assets"
            parts = []
            if buy_signals:
                buy_syms = ', '.join(s['symbol'] for s in buy_signals)
                parts.append(f"BUY signals: {buy_syms}")
            if sell_signals:
                sell_syms = ', '.join(s['symbol'] for s in sell_signals)
                parts.append(f"SELL signals: {sell_syms}")
            if not parts:
                msg = f"Scanned {scan_count} assets. No actionable trade setups this cycle."
            else:
                ticket_count = len(tickets)
                msg = f"Scanned {scan_count} assets. {ticket_count} ticket(s) created.\n" + '\n'.join(parts)
            toast = Notification(app_id="Zeus Crypto Weekend Scan", title=title, msg=msg)
            toast.set_audio(audio.Default, loop=False)
            toast.show()
        except Exception:
            pass

    def _save_alert(self, alert):
        alert['timestamp'] = datetime.now(timezone.utc).isoformat()
        self.alerts_this_cycle.append(alert)
        with open(ALERT_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(alert, ensure_ascii=False) + '\n')
        self.cursor.execute(
            'INSERT INTO insights (type, symbol, broker, detail, timestamp) VALUES (?, ?, ?, ?, ?)',
            (alert['type'], alert['symbol'], alert.get('broker', ''), alert['reason'], alert['timestamp'])
        )
        self.conn.commit()

    def _create_ticket(self, signal):
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        ticket_id = f"CRYPTO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{signal['symbol']}"
        symbol = signal['symbol']
        # Broker anticipation: if symbol is tradeable on eToro, prefer eToro for practice
        symbol_norm = symbol.replace('-USD', '').upper()
        try:
            symbol_map = json.loads(ETORO_SYMBOL_MAP.read_text(encoding='utf-8'))
            if symbol_norm in symbol_map or symbol in symbol_map:
                broker = signal.get('broker', 'ETORO')
            else:
                broker = signal.get('broker', 'KRAKEN')
        except Exception:
            broker = signal.get('broker', 'KRAKEN')
        urgency = signal.get('urgency', 'MEDIUM')
        direction = signal.get('direction', 'LONG')
        entry = signal.get('price', 0)
        size = signal.get('suggested_size', 0)
        mt5_terminal = MT5_TERMINALS.get(broker, '') if broker in MT5_TERMINALS else ''

        # Size guard: hard cap unless broker explicitly allows larger
        if broker in ('CAPITAL_RIGHT', 'FTMO_LEFT'):
            max_size_by_equity = (470.0 if broker == 'CAPITAL_RIGHT' else 200000.0) * 0.01
            size = min(size, max_size_by_equity)
        else:
            size = min(size, MAX_POSITION_USD)

        if direction == 'LONG':
            sl = entry * 0.92 if entry else 0
            tp1 = entry * 1.10 if entry else 0
            tp2 = entry * 1.20 if entry else 0
        else:
            sl = entry * 1.08 if entry else 0
            tp1 = entry * 0.90 if entry else 0
            tp2 = entry * 0.80 if entry else 0

        self.cursor.execute('''
            INSERT INTO dca_tickets
            (ticket_id, symbol, asset_type, broker, direction, order_type,
             entry, sl, tp1, tp2, size, grade, score, urgency, status, mt5_terminal, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ticket_id, symbol, 'CRYPTO', broker, direction, 'LIMIT',
               entry, sl, tp1, tp2, size, signal.get('grade'), signal.get('score'), urgency, 'READY', mt5_terminal, now_str))
        self.conn.commit()
        return {
            'ticket_id': ticket_id,
            'symbol': symbol,
            'asset_type': 'CRYPTO',
            'broker': broker,
            'direction': direction,
            'order_type': 'LIMIT',
            'entry': entry,
            'sl': sl,
            'tp1': tp1,
            'tp2': tp2,
            'size': size,
            'grade': signal.get('grade'),
            'score': signal.get('score'),
            'urgency': urgency,
            'status': 'READY',
            'mt5_terminal': mt5_terminal,
        }

    def _write_ticket_file(self, tickets):
        if not tickets:
            return
        lines = []
        lines.append(f"# Weekend Crypto DCA Auto-Tickets\n**Generated:** {datetime.now(timezone.utc).isoformat()}  ")
        lines.append(f"**Tickets:** {len(tickets)}  \n")
        lines.append("---\n")

        lines.append("## MT5 Manual Tickets\n")
        for t in tickets:
            if t.get('mt5_terminal'):
                lines.append(f"### {t['ticket_id']} — {t['symbol']} ({t['broker']})")
                lines.append(f"- **Terminal:** {t['mt5_terminal']}")
                if t['broker'] == 'FTMO_LEFT':
                    lines.append("- **Login:** REDACTED / **Server:** REDACTED-SERVER")
                elif t['broker'] == 'CAPITAL_RIGHT':
                    lines.append("- **Login:** 1028685 / **Server:** Capital.ComBah-Demo")
                lines.append(f"- **Symbol:** {t['symbol']}USD")
                lines.append(f"- **Type:** {t['direction']} {t['order_type']}")
                lines.append(f"- **Entry:** {t['entry']}")
                lines.append(f"- **SL:** {t['sl']}")
                lines.append(f"- **TP1:** {t['tp1']}")
                lines.append(f"- **TP2:** {t['tp2']}")
                lines.append(f"- **Size:** {t['size']}")
                lines.append(f"- **Comment:** Weekend Crypto DCA | Urgency: {t['urgency']}")
                lines.append("")

        lines.append("## API-Ready Payloads\n")
        for t in tickets:
            if t['broker'] == 'KRAKEN':
                payload = {
                    "pair": f"{t['symbol']}USD",
                    "type": "buy",
                    "ordertype": "limit",
                    "price": str(t['entry']),
                    "volume": str(t['size']),
                    "userref": int(datetime.now(timezone.utc).timestamp()) % 1000000,
                }
                lines.append(f"### {t['ticket_id']} — KRAKEN AddOrder\n")
                lines.append("```json")
                lines.append(json.dumps(payload, indent=2))
                lines.append("```\n")

        lines.append("## Ticket Summary\n")
        lines.append("| Ticket | Symbol | Asset | Broker | Entry | SL | TP1 | TP2 | Size | Grade | Score | Urgency | Status |")
        lines.append("|--------|--------|-------|--------|-------|----|-----|-----|------|-------|-------|---------|--------|")
        for t in tickets:
            grade = t.get('grade') or ''
            score = t.get('score')
            score_str = f"{score:.1f}" if isinstance(score, (int, float)) else ''
            lines.append(
                f"| {t['ticket_id']} | {t['symbol']} | CRYPTO | {t['broker']} | "
                f"{t['entry']} | {t['sl']} | {t['tp1']} | {t['tp2']} | {t['size']} | "
                f"{grade} | {score_str} | {t['urgency']} | {t['status']} |"
            )
        lines.append("")
        lines.append(f"*Auto-generated at {datetime.now(timezone.utc).isoformat()}*")

        TICKET_FILE.write_text('\n'.join(lines), encoding='utf-8')
        print(f'Wrote {len(tickets)} weekend crypto tickets to {TICKET_FILE}')

    def run_cycle(self):
        print(f"\n=== WEEKEND CRYPTO SCAN CYCLE {datetime.now(timezone.utc).isoformat()} ===")
        print(f"Scanning {len(self.CRYPTO_UNIVERSE)} assets")

        # Fetch CoinGecko simple prices with hard time budget
        import time as _time
        cg_start = _time.time()
        cg_data = {}
        try:
            cg_data = self._coingecko_simple()
        except Exception as e:
            print(f"CoinGecko fetch failed: {e}")
        cg_elapsed = _time.time() - cg_start
        print(f"CoinGecko: {len(cg_data)} assets fetched in {cg_elapsed:.1f}s")
        if cg_elapsed > 30:
            print("CoinGecko fetch exceeded time budget; proceeding with partial data only")

        signals = []
        scan_results = []

        # Sector coverage tracking
        sector_coverage = {}

        for symbol in self.CRYPTO_UNIVERSE:
            cg_id = COINGECKO_ID_MAP.get(symbol, symbol.lower())
            cg = cg_data.get(cg_id, {})
            yf = self._yf_crypto_data(symbol)

            # Get price from either source
            price = cg.get('usd', 0)
            if (not price or price <= 0) and yf:
                price = yf.get('price', 0)

            # Skip only if no data at all
            if not price or price <= 0:
                continue

            scored = self._score_crypto(symbol, cg, yf)
            scored['symbol'] = symbol
            scored['price_usd'] = price
            scored['change_24h_pct'] = yf['change_24h_pct'] if yf else (cg.get('usd_24h_change') or 0)
            scored['change_7d_pct'] = yf['change_7d_pct'] if yf else 0
            scored['volume_24h'] = yf['volume_24h'] if yf else 0
            scored['volume_7d_avg'] = yf['volume_7d_avg'] if yf else 0
            scored['funding_rate'] = 0
            scored['market_cap'] = cg.get('usd_market_cap', 0)
            scored['timestamp'] = datetime.now(timezone.utc).isoformat()

            # Track sector coverage
            sector = self._sector_for_symbol(symbol)
            if sector:
                sector_coverage[sector] = sector_coverage.get(sector, 0) + 1

            scan_results.append(scored)

            # Check buy setup with safe defaults
            is_buy = False
            signal_type = []
            urgency = 'LOW'

            rsi_val = scored['rsi_14'] if scored['rsi_14'] is not None else 50
            chg24 = scored['change_24h_pct'] if scored['change_24h_pct'] is not None else 0
            chg7d = scored['change_7d_pct'] if scored['change_7d_pct'] is not None else 0
            vol_r = scored['volume_ratio'] if scored['volume_ratio'] is not None else 1

            has_real_signal = (chg7d != 0) or (rsi_val < 45) or (chg24 < -3) or (rsi_val > 55) or (chg24 > 3)

            if rsi_val < BUY_SETUP_TRIGGERS['rsi_oversold']:
                is_buy = True
                signal_type.append('RSI_OVERSOLD')
                urgency = 'HIGH'
            if chg24 <= BUY_SETUP_TRIGGERS['price_drop_24h_pct']:
                is_buy = True
                signal_type.append('24H_DUMP')
                urgency = 'HIGH'
            if chg7d <= BUY_SETUP_TRIGGERS['price_drop_7d_pct']:
                is_buy = True
                signal_type.append('7D_DUMP')
                if urgency != 'HIGH':
                    urgency = 'MEDIUM'
            if vol_r >= BUY_SETUP_TRIGGERS['volume_spike_mult']:
                is_buy = True
                signal_type.append('VOLUME_SPIKE')
                urgency = 'HIGH'
            if scored['grade'] == 'ACCUMULATE':
                is_buy = True
                signal_type.append('SCORECARD_ACCUMULATE')
                if urgency != 'HIGH':
                    urgency = 'MEDIUM'
            elif scored['grade'] == 'AVOID':
                is_buy = False
                signal_type = []

            if is_buy and has_real_signal and price > 0 and scored['grade'] != 'AVOID':
                sig = {
                    'type': 'WEEKEND_CRYPTO_BUY',
                    'symbol': symbol,
                    'asset_type': 'CRYPTO',
                    'broker': self._pick_broker(symbol),
                    'direction': 'LONG',
                    'reason': f"Buy setup: {', '.join(signal_type)} | RSI={rsi_val:.1f} 24h={chg24:.1f}% 7d={chg7d:.1f}% Grade={scored['grade']}",
                    'urgency': urgency,
                    'price': price,
                    'suggested_size': 100.0 / max(price, 0.01),  # ~$100 position
                    'score': scored['score'],
                    'grade': scored['grade'],
                    'rsi': scored['rsi_14'],
                    'change_24h_pct': scored['change_24h_pct'],
                    'change_7d_pct': scored['change_7d_pct'],
                }
                signals.append(sig)
                self._save_alert(sig)
                ticket = self._create_ticket(sig)
                self.tickets_this_cycle.append(ticket)
                self._send_trade_toast(sig, ticket)
                self._bridge_to_etoro_demo(sig, ticket)

            # Check sell/short setup: overbought + strong move + volume
            is_short = False
            short_type = []
            short_urgency = 'LOW'

            if rsi_val > SHORT_SETUP_TRIGGERS['rsi_overbought']:
                is_short = True
                short_type.append('RSI_OVERBOUGHT')
                short_urgency = 'HIGH'
            if chg24 >= SHORT_SETUP_TRIGGERS['price_rise_24h_pct']:
                is_short = True
                short_type.append('24H_PUMP')
                short_urgency = 'HIGH'
            if chg7d >= SHORT_SETUP_TRIGGERS['price_rise_7d_pct']:
                is_short = True
                short_type.append('7D_PUMP')
                if short_urgency != 'HIGH':
                    short_urgency = 'MEDIUM'
            if vol_r >= SHORT_SETUP_TRIGGERS['volume_spike_mult']:
                is_short = True
                short_type.append('VOLUME_SPIKE')
                short_urgency = 'HIGH'

            broker_ok = BROKER_SHORT_CAPABLE.intersection(BROKER_ROUTING_CRYPTO)
            if is_short and has_real_signal and price > 0 and broker_ok:
                short_broker = sorted(broker_ok)[0]
                short_sig = {
                    'type': 'WEEKEND_CRYPTO_SELL',
                    'symbol': symbol,
                    'asset_type': 'CRYPTO',
                    'broker': short_broker,
                    'direction': 'SHORT',
                    'reason': f"Short setup: {', '.join(short_type)} | RSI={rsi_val:.1f} 24h={chg24:.1f}% 7d={chg7d:.1f}% Grade={scored['grade']}",
                    'urgency': short_urgency,
                    'price': price,
                    'suggested_size': 100.0 / max(price, 0.01),
                    'score': scored['score'],
                    'grade': scored['grade'],
                    'rsi': scored['rsi_14'],
                    'change_24h_pct': scored['change_24h_pct'],
                    'change_7d_pct': scored['change_7d_pct'],
                }
                signals.append(short_sig)
                self._save_alert(short_sig)
                short_ticket = self._create_ticket(short_sig)
                self.tickets_this_cycle.append(short_ticket)
                self._send_trade_toast(short_sig, short_ticket)
                self._bridge_to_etoro_demo(short_sig, short_ticket)

            # Save to DB
            self.cursor.execute('''
                INSERT INTO crypto_scan_results
                (symbol, price_usd, change_24h_pct, change_7d_pct, rsi_14,
                 volume_24h, volume_7d_avg, funding_rate, market_cap,
                 score_grade, buy_setup, signal_type, urgency, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                symbol, price, scored['change_24h_pct'], scored['change_7d_pct'],
                scored['rsi_14'], scored['volume_24h'], scored['volume_7d_avg'],
                0, scored['market_cap'], scored['grade'], is_buy,
                ','.join(signal_type), urgency, datetime.now(timezone.utc).isoformat()
            ))

        self.conn.commit()

        # Summary
        buy_setups = [s for s in scan_results if s['grade'] in ['ACCUMULATE', 'MIXED']]
        sell_signals = [s for s in signals if s.get('type') == 'WEEKEND_CRYPTO_SELL']
        buy_signals = [s for s in signals if s.get('type') == 'WEEKEND_CRYPTO_BUY']
        print(f"\nScan complete: {len(scan_results)} assets, {len(buy_signals)} buy signals, {len(sell_signals)} sell signals")
        print(f"Buy setups: {len(buy_setups)}")
        for s in sorted(buy_setups, key=lambda x: x.get('score') or 0, reverse=True)[:10]:
            rsi = s.get('rsi_14')
            c24 = s.get('change_24h_pct')
            c7d = s.get('change_7d_pct')
            score = s.get('score')
            print(f"  {s['symbol']}: ${s['price_usd']:.4f} RSI={rsi if rsi is not None else 'NA'} 24h={c24 if c24 is not None else 'NA'}% 7d={c7d if c7d is not None else 'NA'}% Grade={s['grade']} Score={score if score is not None else 'NA'}")

        if sell_signals:
            print("\nSell/short setups:")
            for s in sorted(sell_signals, key=lambda x: x.get('score') or 0, reverse=True)[:10]:
                rsi = s.get('rsi')
                c24 = s.get('change_24h_pct')
                c7d = s.get('change_7d_pct')
                print(f"  {s['symbol']}: ${s['price']:.4f} RSI={rsi if rsi is not None else 'NA'} 24h={c24 if c24 is not None else 'NA'}% 7d={c7d if c7d is not None else 'NA'}% Broker={s['broker']} Dir={s['direction']}")

        if self.tickets_this_cycle:
            self._write_ticket_file(self.tickets_this_cycle)

        self._send_cycle_summary(len(scan_results), buy_signals, sell_signals, self.tickets_this_cycle)

        # Sector coverage summary
        if sector_coverage:
            print("\nSector coverage:")
            for sec in sorted(sector_coverage):
                print(f"  {sec}: {sector_coverage[sec]} assets")
            print(f"  TOTAL sectors covered: {len(sector_coverage)}")

        return signals

    def run_continuous(self, interval_minutes=15):
        print(f'Starting WEEKEND CRYPTO SCANNER ({interval_minutes}m)')
        print(f'Universe: {len(CRYPTO_UNIVERSE)} assets')
        print('Press Ctrl+C to stop\n')
        try:
            while True:
                self.run_cycle()
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location('toast_to_etoro_demo', str(BASE_FIRM / 'scripts' / 'toast_to_etoro_demo.py'))
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    placed, failed = mod.process_queue()
                    if placed or failed:
                        print(f'[etoro-bridge] queued placed={placed} failed={failed}')
                    mod.mark_to_market()
                except Exception as e:
                    print(f'[etoro-bridge] loop error: {e}')
                time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            print('\nStopping scanner...')
        finally:
            self.conn.close()


if __name__ == '__main__':
    scanner = WeekendCryptoScanner()
    if '--continuous' in sys.argv:
        try:
            idx = sys.argv.index('--continuous')
            interval = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else 15
        except (ValueError, IndexError):
            interval = 15
        scanner.run_continuous(interval)
    else:
        sigs = scanner.run_cycle()
        print(f'\nFinal signals: {len(sigs)}')
        for sig in sigs[:10]:
            print(f'  {sig["symbol"]}: {sig["grade"]} @ ${sig["price"]:.4f}')

        # Whale overlap analysis
        whale_path = BASE_FIRM / 'workflow' / 'whale_investor_tracker.json'
        if whale_path.exists():
            try:
                whale_data = json.loads(whale_path.read_text(encoding='utf-8'))
                whale_matrix = whale_data.get('matrix', {})
                whale_signals = []
                for sig in sigs:
                    symbol = sig['symbol']
                    for whale, info in whale_matrix.items():
                        if symbol in info.get('watchlist_overlap', []):
                            whale_signals.append({
                                'symbol': symbol,
                                'whale': whale,
                                'entity': info.get('entity'),
                                'style': info.get('style'),
                                'grade': sig['grade']
                            })
                if whale_signals:
                    print('\n=== WHALE OVERLAP SIGNALS ===')
                    for ws in whale_signals:
                        print(f'  {ws["symbol"]}: {ws["whale"]} ({ws["entity"]}) - {ws["grade"]}')
                else:
                    print('\nNo whale overlap on current signals')
            except Exception as e:
                print(f'\nWhale analysis failed: {e}')