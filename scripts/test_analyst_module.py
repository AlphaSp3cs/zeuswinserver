import sys, types, importlib.util, urllib.request, json

# Load module with patched urlopen
import urllib.request
orig_urlopen = urllib.request.urlopen
class FakeResp:
    def __init__(self,data,status=200):
        self.data = data.encode('utf-8') if isinstance(data,str) else data
        self.status = status
        self.reason = 'OK'
    def read(self):
        return self.data
    def readinto(self, b): return 0
    def __enter__(self): return self
    def __exit__(self,*args): return False

def fake_urlopen(req, timeout=20):
    url = req.full_url if hasattr(req,'full_url') else str(req)
    if 'coingecko' in url:
        return FakeResp(json.dumps([{'id':'btc','symbol':'btc','name':'Bitcoin','current_price':70000,'market_cap':1400000000000,'total_volume':50000000,'price_change_percentage_24h':-4.4}]))
    if 'stockanalysis.com/stocks/AAPL' in url:
        return FakeResp('<a="/stocks/aapl/forecast/"></a><td class="x"><p>318.81 (-5.69%)</p><div>Analyst Consensus: <span>Buy</span></div>',200)
    if 'stockanalysis.com/stocks/ETH' in url:
        return FakeResp('<a></a><td class="x"><p>4200.12 (+12.34%)</p><div>Analyst Consensus: <span>Strong Buy</span></div>',200)
    if 'marketbeat' in url:
        return FakeResp('<div>Consensus Rating <span>Buy</span> 320</div>')
    if 'tipranks' in url:
        return FakeResp('<span>Analyst Consensus: Hold</span><span>Target 4100</span>')
    return orig_urlopen(req, timeout=timeout)

urllib.request.urlopen = fake_urlopen

spec = importlib.util.spec_from_file_location('sp', r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\loads\Scan protocol\sector_scan_protocol.py')
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)
print('module loaded ok')




print(sp._fetch_autoscore_for_symbol('AAPL'))
print(sp._fetch_autoscore_for_symbol('ETH'))
