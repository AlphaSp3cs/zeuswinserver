#!/usr/bin/env python3
"""scan - run all-sector scan with options for dayshift/nightshift backtesting."""
import sys
import subprocess
from pathlib import Path

FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
SCRIPT = FIRM / 'scripts' / 'all_sector_scan_with_options.py'

if __name__ == '__main__':
    sys.exit(subprocess.run([sys.executable, str(SCRIPT)]).returncode)
