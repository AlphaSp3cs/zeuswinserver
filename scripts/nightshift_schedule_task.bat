@echo off
REM Create Windows scheduled task for nightshift autopilot
REM Runs every 15 minutes from 18:00 to 09:00 ET
schtasks /create /tn "OuroTaurus_Nightshift" /tr "\"C:\Users\bravo-usr1\AppData\Local\Microsoft\WindowsApps\python3.exe\" \"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\scripts\nightshift_autopilot.py\"" /sc minute /mo 15 /st 18:00 /et 09:00 /f
echo.
echo Task created. Verify with: schtasks /query /tn "OuroTaurus_Nightshift" /fo list /v
echo.
echo To stop manually: schtasks /end /tn "OuroTaurus_Nightshift"
echo To delete: schtasks /delete /tn "OuroTaurus_Nightshift" /f
pause
