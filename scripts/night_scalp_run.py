import json, math, time
from datetime import datetime, timezone
import MetaTrader5 as mt5
SYMBOLS = ['BTCUSD','ETHUSD','SOLUSD','ADAUSD','FETUSD']
RATES_COUNT = 200
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ATR_PERIOD = 14
RISK_PCT = 0.02
PORTFOLIO_RISK_PCT = 0.08
OUT_PATH = r'C:\Users\bravo-usr1\.hermes\data\ourotau_scalp_session.json'
LOG_OUT = []
def log(msg):
    LOG_OUT.append(msg)
    print(msg)
def ema(data, period):
    k = 2 / (period + 1)
    res = [sum(data[:period]) / period]
    for price in data[period:]:
        res.append(price * k + res[-1] * (1 - k))
    return res
def compute_rsi(closes, period=14):
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi = [100 - (100 / (1 + (avg_gain / avg_loss))) if avg_loss != 0 else 100.0]
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
        rsi.append(100 - (100 / (1 + rs)))
    return rsi
def compute_macd(closes, fast=12, slow=26, signal=9):
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    offset = slow - fast
    macd_line = [ema_fast[i+offset] - ema_slow[i] for i in range(len(ema_slow))]
    signal_line = ema(macd_line, signal)
    histogram = [macd_line[i+signal-1] - signal_line[i] for i in range(len(signal_line))]
    return macd_line, signal_line, histogram
def compute_bb(closes, period=20, std=2):
    mid = []
    upper = []
    lower = []
    for i in range(len(closes)):
        if i < period - 1:
            continue
        window = closes[i-period+1:i+1]
        m = sum(window) / period
        variance = sum((x - m)**2 for x in window) / period
        s = math.sqrt(variance)
        mid.append(m)
        upper.append(m + std * s)
        lower.append(m - std * s)
    return mid, upper, lower
def compute_atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    atr = [sum(trs[:period]) / period]
    for i in range(period, len(trs)):
        atr.append((atr[-1] * (period - 1) + trs[i]) / period)
    return atr
def compute_sma(closes, period=50):
    sma = []
    for i in range(len(closes)):
        if i < period - 1:
            continue
        sma.append(sum(closes[i-period+1:i+1]) / period)
    return sma
def main():
    if not mt5.initialize():
        log('MT5 init failed: ' + str(mt5.last_error()))
        return
    acc = mt5.account_info()
    equity = float(acc.equity)
    balance = float(acc.balance)
    max_trade_risk = equity * RISK_PCT
    max_portfolio_risk = equity * PORTFOLIO_RISK_PCT
    log('MT5 equity=' + str(round(equity,2)) + ' balance=' + str(round(balance,2)) + ' max_trade_risk=' + str(round(max_trade_risk,2)) + ' max_portfolio_risk=' + str(round(max_portfolio_risk,2)))
    signals = []
    for sym in SYMBOLS:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, RATES_COUNT)
        if rates is None or len(rates) < 100:
            log(sym + ': insufficient data ' + str(len(rates) if rates else 0))
            continue
        closes = [r['close'] for r in rates]
        highs = [r['high'] for r in rates]
        lows = [r['low'] for r in rates]
        ticks = mt5.symbol_info_tick(sym)
        info = mt5.symbol_info(sym)
        if not ticks or not info:
            log(sym + ': no tick/info')
            continue
        price = ticks.ask

        rsi_arr = compute_rsi(closes, RSI_PERIOD)
        macd_line, signal_line, hist = compute_macd(closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
        mid, upper, lower = compute_bb(closes, BB_PERIOD, BB_STD)
        atr_arr = compute_atr(highs, lows, closes, ATR_PERIOD)
        sma_arr = compute_sma(closes, 50)

        def last(arr):
            return arr[-1] if arr else None

        rsi = last(rsi_arr)
        macd_hist = last(hist)
        bb_pos = None
        if len(mid) >= 1:
            lm = mid[-1]
            lu = upper[-1]
            ll = lower[-1]
            bb_pos = (price - ll) / (lu - ll) if lu != ll else 0.5
        atr = last(atr_arr)
        sma = last(sma_arr)

        log(sym + ': price=' + str(round(price,4)) + ' RSI=' + str(round(rsi,1) if rsi is not None else None) + ' MACD_hist=' + str(round(macd_hist,4) if macd_hist is not None else None) + ' BB=' + str(round(bb_pos,2) if bb_pos is not None else None) + ' ATR=' + str(round(atr,4) if atr is not None else None) + ' SMA50=' + str(round(sma,4) if sma is not None else None))
        score = 0
        if sma is not None and price > sma:
            score += 1
        if rsi is not None and 50 < rsi < 70:
            score += 1
        if macd_hist is not None and macd_hist > 0:
            score += 1
        if bb_pos is not None and bb_pos > 0.5:
            score += 1
        if atr is not None and 0.005 * price < atr < 0.05 * price:
            score += 1

        direction = None
        if score >= 4:
            direction = 'LONG'
        elif score <= 1:
            direction = 'SHORT'
        else:
            direction = None

        log('  score=' + str(score) + ' direction=' + str(direction))

        if direction:
            if direction == 'LONG':
                sl = round(price - 2 * atr, info.digits)
                tp = round(price + 4 * atr, info.digits)
                risk_per_unit = price - sl
                entry_price = price
                order_type = mt5.ORDER_TYPE_BUY
            else:
                sl = round(price + 2 * atr, info.digits)
                tp = round(price - 4 * atr, info.digits)
                risk_per_unit = sl - price
                bid = ticks.bid
                entry_price = bid if bid else price
                order_type = mt5.ORDER_TYPE_SELL
            if risk_per_unit <= 0:
                log('  invalid risk_per_unit ' + str(risk_per_unit))
                continue
            tick_size = info.trade_tick_size or info.point
            tick_value = info.trade_tick_value or 0.0
            if tick_size <= 0 or tick_value <= 0:
                log('  bad tick info')
                continue
            risk_per_lot = risk_per_unit * (tick_value / tick_size)
            raw_vol = max_trade_risk / risk_per_lot
            step = float(info.volume_step) if info.volume_step else 0.01
            vol = round(raw_vol / step) * step
            vol = max(info.volume_min, min(info.volume_max, vol))
            actual_risk = risk_per_unit * (tick_value / tick_size) * vol
            signals.append({
                'symbol': sym,
                'direction': direction,
                'price': price,
                'sl': sl,
                'tp': tp,
                'volume': vol,
                'risk_usd': round(actual_risk, 2),
                'score': score,
                'entry_price': entry_price,
                'order_type': order_type,
            })
            log('  candidate: ' + sym + ' ' + direction + ' vol=' + str(vol) + ' sl=' + str(sl) + ' tp=' + str(tp) + ' risk=' + str(round(actual_risk,2)))
    placed = []
    total_new_risk = 0.0
    for sig in signals:
        if total_new_risk + sig['risk_usd'] > max_portfolio_risk:
            log('Reject ' + sig['symbol'] + ': portfolio risk limit')
            continue
        sym = sig['symbol']
        order_type = sig['order_type']
        entry_price = sig['entry_price']
        sl = sig['sl']
        tp = sig['tp']
        vol = sig['volume']
        req = {
            'action': mt5.TRADE_ACTION_DEAL,
            'symbol': sym,
            'volume': float(vol),
            'type': order_type,
            'price': float(entry_price),
            'sl': float(sl),
            'tp': float(tp),
            'deviation': 20,
            'magic': 20260726,
            'comment': 'OURO_NIGHT_SCALP',
            'type_time': mt5.ORDER_TIME_GTC,
            'type_filling': mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        status = None
        ticket = None
        deal = None
        retcode = None
        comment = None
        if res is None:
            status = 'failed_no_response'
        else:
            retcode = int(res.retcode)
            comment = str(res.comment)
            ticket = int(res.order) if res.order else None
            deal = int(res.deal) if res.deal else None
            if retcode in (10009, 10008, 10004):
                status = 'placed'
            else:
                status = 'failed'
        log('Order ' + sym + ' ' + sig['direction'] + ': status=' + str(status) + ' retcode=' + str(retcode) + ' ticket=' + str(ticket) + ' deal=' + str(deal) + ' comment=' + str(comment))
        placed.append({
            'symbol': sym,
            'direction': sig['direction'],
            'status': status,
            'entry': entry_price,
            'sl': sl,
            'tp': tp,
            'volume': vol,
            'risk_usd': sig['risk_usd'],
            'ticket': ticket,
            'deal': deal,
            'retcode': retcode,
            'comment': comment,
        })
        total_new_risk += sig['risk_usd']
        time.sleep(2)
    positions = mt5.positions_get()
    pos_list = []
    if positions:
        for p in positions:
            if int(p.magic) == 20260726:
                pos_list.append({
                    'ticket': int(p.ticket),
                    'symbol': p.symbol,
                    'type': 'LONG' if p.type == 0 else 'SHORT',
                    'volume': float(p.volume),
                    'sl': float(p.sl) if p.sl else None,
                    'tp': float(p.tp) if p.tp else None,
                    'profit': round(float(p.profit), 2)
                })
    log('Positions after run: ' + str(len(pos_list)))
    for p in pos_list:
        log('  ' + p['symbol'] + ' ' + p['type'] + ' vol=' + str(p['volume']) + ' profit=' + str(p['profit']))
    venue_status = {
        'Alpaca_equities': 'market_closed_weekend',
        'Alpaca_crypto': 'auth_invalid',
        'Kraken_crypto': 'auth_invalid',
        'MT5_FTMO': 'open'
    }
    portfolio_risk = {
        'equity': equity,
        'confirmed_risk': total_new_risk,
        'unverified_pending_risk': 0.0,
        'new_risk_this_run': total_new_risk,
        'total_risk_confirmed_only': total_new_risk,
        'total_risk_if_pending_filled': total_new_risk,
        'max_limit': max_portfolio_risk
    }
    session = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'venue_status': venue_status,
        'previous_pending_trades': [],
        'scan_results': [s['symbol'] + '_' + s['direction'] + '_score' + str(s['score']) for s in signals],
        'planned_trades': [],
        'portfolio_risk': portfolio_risk,
        'summary': {
            'placed': len([p for p in placed if p['status']=='placed']),
            'rejected': len([p for p in placed if p['status']!='placed']),
            'planned': 0,
            'reason': 'Scanned and executed via MT5; Alpaca/Kraken auth blocked'
        }
    }
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(session, f, indent=2)
    log('Session memory updated: ' + OUT_PATH)
    mt5.shutdown()

    print(json.dumps({'log': LOG_OUT, 'placed': placed, 'portfolio_risk': portfolio_risk}, indent=2, default=str))
if __name__ == '__main__':
    main()