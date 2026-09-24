import MetaTrader5 as mt5
import time

MT5_PATH = r'REDACTED-PATH'
LOGIN = int(os.environ.get('FTMO_MT5_LOGIN', '0'))
SERVER = os.environ.get('FTMO_MT5_SERVER', '')

def connect():
    if not mt5.initialize(path=MT5_PATH, login=LOGIN, server=SERVER, timeout=20):
        err = mt5.last_error()
        print(f"initialize_failed: {err}")
        return None
    print(f"Connected to account {LOGIN} on {SERVER}")
    return mt5

def modify_sl_tp(ticket, symbol, typ, volume, price_open):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"  Symbol {symbol} not found, selecting...")
        if not mt5.symbol_select(symbol, True):
            print(f"  Failed to select {symbol}")
            return False
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            print(f"  Symbol info still None for {symbol}")
            return False
    point = symbol_info.point
    digits = symbol_info.digits

    # Calculate SL and TP distances: use 0.5% of price_open for SL, TP/SL ratio ~1.67
    sl_distance = price_open * 0.005  # 0.5%
    tp_distance = sl_distance * 1.67

    if typ == mt5.ORDER_TYPE_BUY:  # LONG
        sl = price_open - sl_distance
        tp = price_open + tp_distance
    else:  # ORDER_TYPE_SELL (SHORT)
        sl = price_open + sl_distance
        tp = price_open - tp_distance

    # Round to the symbol's digits
    sl = round(sl, digits)
    tp = round(tp, digits)

    print(f"  Setting SL={sl}, TP={tp} (digits={digits})")

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl": sl,
        "tp": tp,
        "symbol": symbol,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"  FAILED: retcode={result.retcode}, comment={result.comment}")
        return False
    else:
        print(f"  SUCCESS")
        return True

def main():
    mt5 = connect()
    if mt5 is None:
        return

    try:
        info = mt5.account_info()
        if info:
            print(f"Account: {info.login}, Balance: {info.balance}, Equity: {info.equity}")

        positions = mt5.positions_get()
        print(f"Total open positions: {len(positions)}")
        modified_count = 0
        for pos in positions:
            ticket = pos.ticket
            symbol = pos.symbol
            typ = pos.type  # 0 for buy, 1 for sell
            volume = pos.volume
            price_open = pos.price_open
            sl = pos.sl
            tp = pos.tp
            if sl == 0.0 or tp == 0.0:
                typ_str = "BUY" if typ == mt5.ORDER_TYPE_BUY else "SELL"
                print(f"Ticket {ticket}: {symbol} {typ_str} vol={volume} open={price_open:.5f} SL={sl} TP={tp} -> needs SL/TP")
                if modify_sl_tp(ticket, symbol, typ, volume, price_open):
                    modified_count += 1
                time.sleep(0.5)
            else:
                # Optionally, we could verify that SL/TP are reasonable, but skip for now
                pass
        print(f"Modified {modified_count} positions.")
    finally:
        mt5.shutdown()
        print("Disconnected from MT5")

if __name__ == "__main__":
    main()