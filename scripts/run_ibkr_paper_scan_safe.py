#!/usr/bin/env python3
"""Run the IBKR paper scan without placing orders."""
import sys, json, types
from pathlib import Path

# Patch IB.placeOrder to no-op before importing the scan module.
class _NoOpIB:
    def __init__(self, real_ib):
        self._real = real_ib
        self.isConnected = real_ib.isConnected
    def placeOrder(self, *a, **kw):
        class _Dummy:
            orderId = 0
            status = 'SKIPPED_DRY_RUN'
            filled = None
            avgFillPrice = None
        return _Dummy()

# Monkey patch on the module level after import.
mod_name = 'ibkr_paper_scan_20260723'
if mod_name not in sys.modules:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        mod_name,
        r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\_archive_20260823\ibkr_paper_scan_20260723.py'
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    # Before execution, patch IB class used inside module.
    import ib_insync
    sys.path.insert(0, r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\vault')
    sys.path.insert(0, r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
    real_place_order = ib_insync.IB.placeOrder
    def _noop_place_order(self, *a, **kw):
        class _Dummy:
            orderId = 0
            status = 'SKIPPED_DRY_RUN'
            filled = None
            avgFillPrice = None
        return _Dummy()
    ib_insync.IB.placeOrder = _noop_place_order
    spec.loader.exec_module(mod)
else:
    mod = sys.modules[mod_name]

# Ensure any later direct IB class usage from ib_insync is also patched.
import ib_insync
ib_insync.IB.placeOrder = lambda self, *a, **kw: type('OBJ', (), {'orderId':0,'status':'SKIPPED_DRY_RUN','filled':None,'avgFillPrice':None})()

# Run scan
mod.main()
