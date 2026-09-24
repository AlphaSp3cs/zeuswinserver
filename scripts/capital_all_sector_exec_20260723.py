
#!/usr/bin/env python3
"""Capital/MT5 all-sector scan with executable plan and hard SL+TP.
Persists proposed trades to proposed_trades_<date>_CAPITAL.json.
"""
import json, math, datetime, os
from pathlib import Path
import MetaTrader5

MT5_PATH = r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe'
LOGIN = int(os.environ.get('CAPITAL_MT5_LOGIN', '0'))
SERVER = os.environ.get('CAPITAL_MT5_SERVER', '')
DAY = datetime.date.today().isoformat()
PLAN_PATH = Path('proposed_trades_{}_CAPITAL.json'.format(DAY))
MAX_PORTFOLIO_RISK_PCT = 0.08
MAX_RISK_PER_TRADE_PCT = 0.02

UNIVERSE = [
    'EURUSD','GBPUSD','USDJPY','AUDUSD','NZDUSD','USDCAD','USDCHF',
    'BTCUSD','ETHUSD','SOLUSD',
    'SPX500','NAS100','DE30','UK100',
    'XAUUSD','XAGUSD',
]


def market_rates(symbol):
    """Try multiple MT5 history endpoints and return (closes, highs, lows)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        rates = MetaTrader5.copy_rates_from(symbol, MetaTrader5.TIMEFRAME_H1, now - datetime.timedelta(hours=200), 200)
        if rates is not None and len(rates) >= 35:
            return [float(r['close']) for r in rates[-200:]], [float(r['high']) for r in rates[-200:]], [float(r['low']) for r in rates[-200:]], None
        else:
            rates = MetaTrader5.copy_rates_from_pos(symbol, MetaTrader5.TIMEFRAME_H1, 0, 200)
            if rates is not None and len(rates) >= 35:
                return [float(r['close']) for r in rates[-200:]], [float(r['high']) for r in rates[-200:]], [float(r['low']) for r in rates[-200:]], None
    except Exception:
        pass
    return None, None, None, 'insufficient_history'


def is_market_open(symbol):
    """Weekend/off-hours guard for MT5 scanner."""
    try:
        import pytz
        et = pytz.timezone('America/New_York')
        now_et = datetime.datetime.now(et)
        weekday = now_et.weekday()
        if weekday == 6 and now_et.hour >= 17:
            fx_open = True
        elif weekday == 5 and now_et.hour < 17:
            fx_open = True
        elif weekday in (0, 1, 2, 3):
            fx_open = True
        else:
            fx_open = False
        up = symbol.upper()
        if any(k in up for k in ['SPX','NAS','US30','UK100','GER40','DE30','XAU','XAG','USOIL']):
            return False
        if any(k in up for k in ['USD','EUR','GBP','NZD','AUD','CAD','CHF','JPY','BTC','ETH','SOL','UNI','XLM','LTC','AVAX','LINK','AAVE','XTZ','BCH','ADA','NEO','XRP']):
            return fx_open
        return fx_open
    except Exception:
        return True


def queue_pending(symbol, direction, entry, sl, tp, qty, reason):
    pending_path = Path('pending_trades_{}.json'.format(DAY))
    pending = []
    if pending_path.exists():
        try:
            pending = json.loads(pending_path.read_text(encoding='utf-8'))
        except Exception:
            pending = []
    pending.append({
        'symbol': symbol,
        'direction': direction,
        'entry': entry,
        'sl': sl,
        'tp': tp,
        'qty': qty,
        'reason': reason,
        'queued_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
    pending_path.write_text(json.dumps(pending, indent=2, ensure_ascii=False), encoding='utf-8')


def ema(values, span):
    out=[]; mult=2/(span+1); prev=sum(values[:span])/span; out.append(prev)
    for v in values[span:]:
        prev=(v-prev)*mult+prev; out.append(prev)
    return out


def rsi_from_closes(closes, period=14):
    if len(closes)<period+1:
        return None
    deltas=[closes[i]-closes[i-1] for i in range(1,len(closes))]
    up=sum(d for d in deltas if d>0); down=-sum(d for d in deltas if d<0)
    if down==0:
        return 100.0
    rs=(up/period)/(down/period)
    return 100-100/(1+rs)


def macd_from_closes(closes):
    if len(closes)<35:
        return None, None
    ema12=ema(closes,12); ema26=ema(closes,26); offset=len(closes)-len(ema12)
    aligned12=ema12; aligned26=ema26[offset:] if offset>0 else ema26
    macd=[a-b for a,b in zip(aligned12,aligned26)]; signal=ema(macd,9)
    return macd, signal


def atr_from_ohlc(highs, lows, closes, period=14):
    tr=[]; prev=closes[0]
    for h,l,c in zip(highs,lows,closes):
        tr.append(max(h-l, abs(h-prev), abs(l-prev))); prev=c
    if len(tr)<period:
        return None
    tr_ema=ema(tr,period)
    return tr_ema[-1] if tr_ema else None


def size_position(equity, entry, sl):
    risk_dist=abs(entry-sl)
    if risk_dist<=0:
        return 0.01
    qty=equity*MAX_RISK_PER_TRADE_PCT/risk_dist
    return max(0.01, round(qty,2))


def main():
    plan={
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'broker':'CAPITAL',
        'session':'CAPITAL_ALL_SECTOR_20260723',
        'account':{'login':LOGIN,'server':SERVER,'terminal':MT5_PATH},
        'equity': None,
        'balance': None,
        'proposed_trades':[],
        'blocked':[],
        'no_trade_reason': None,
    }

    if not MetaTrader5:
        plan['no_trade_reason']='mt5linux_unavailable'
        with open(PLAN_PATH,'w',encoding='utf-8') as f:
            json.dump(plan, f, indent=2)
        print(json.dumps(plan, ensure_ascii=False))
        return

    mt5 = MetaTrader5
    if not mt5.initialize(path=MT5_PATH, login=LOGIN, server=SERVER):
        # retry once after shutdown to clear IPC timeout
        mt5.shutdown()
        if not mt5.initialize(path=MT5_PATH, login=LOGIN, server=SERVER):
            plan['no_trade_reason']='mt5_init_failed'
            with open(PLAN_PATH,'w',encoding='utf-8') as f:
                json.dump(plan, f, indent=2)
            print(json.dumps(plan, ensure_ascii=False))
            return

    info = mt5.account_info()
    equity = float(getattr(info, 'equity', 0) or 0)
    balance = float(getattr(info, 'balance', 0) or 0)
    plan['equity'] = equity
    plan['balance'] = balance

    proposals=[]
    for sym in UNIVERSE:
        try:
            si = mt5.symbol_info(sym)
            if si is not None:
                mt5.symbol_select(sym, True)
        except Exception:
            pass
        closes, highs, lows, fallback = market_rates(sym)
        if closes is None or len(closes) < 35:
            plan['blocked'].append({'symbol':sym,'reason':'insufficient_history','fallback':fallback})
            continue
        price=closes[-1]
        rsi=rsi_from_closes(closes); macd_line,signal_line=macd_from_closes(closes); atr=atr_from_ohlc(highs,lows,closes)
        if rsi is None or macd_line is None or signal_line is None or atr is None:
            plan['blocked'].append({'symbol':sym,'reason':'indicator_insufficient'})
            continue
        bull=rsi<42 and macd_line[-1]>signal_line[-1] and price>closes[-2]
        bear=rsi>58 and macd_line[-1]<signal_line[-1] and price<closes[-2]
        if not (bull or bear):
            continue
        direction='LONG_BUY' if bull else 'SHORT_SELL'
        entry=price
        sl=entry-bull*2.0*atr+bear*2.0*atr
        tp=entry+bull*2.5*atr-bear*2.5*atr
        rr=abs(tp-entry)/abs(entry-sl) if abs(entry-sl)>0 else 0
        if rr<1.2:
            continue
        if not is_market_open(sym):
            queue_pending(sym, direction, round(entry,4), round(sl,4), round(tp,4), 0, 'market_closed_weekend')
            continue
        qty=size_position(equity,entry,sl)
        proposals.append({
            'symbol':sym,'direction':direction,'entry':round(entry,4),'sl':round(sl,4),'tp':round(tp,4),
            'qty':qty,'rr':round(rr,2),'rsi':round(rsi,2),'atr':round(atr,4),'status':'PROPOSED'
        })

    plan['proposed_trades']=proposals
    if not proposals:
        plan['no_trade_reason']=plan.get('no_trade_reason') or 'no qualifying setups this tick'
    with open(PLAN_PATH,'w',encoding='utf-8') as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print('PLAN_PATH')
    print(str(PLAN_PATH))
    print('PLAN')
    print(json.dumps(plan, ensure_ascii=False))

if __name__=='__main__':
    main()
