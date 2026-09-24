from alpaca_trade_api import REST
import pandas as pd
api=REST('PKKFBUIB2ME4QEL4DC552CASYM','B7UzBja7QK3sZGB1H6pWyviNPCyJed6TBfMSxfZ3Wivb','https://paper-api.alpaca.markets', api_version='v2')
for tf in ['15Min','5Min','1Min']:
    bars=api.get_crypto_bars('BTC/USD',tf,limit=50).df
    print(tf, 'rows', len(bars))
