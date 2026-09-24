@echo off
:: Setup Windows Task Scheduler entries for OuroTaurus Shift Automation
:: Run this script as Administrator once to create all scheduled tasks.

set "PYTHON=C:\Users\bravo-usr1\AppData\Local\Programs\Python\Python313\python.exe"
set "BASE=C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\scripts"
set "TASK_PREFIX=OuroTaurus_Shift"

:: Remove old tasks if they exist
schtasks /delete /tn "%TASK_PREFIX%_Master" /f >nul 2>&1
schtasks /delete /tn "%TASK_PREFIX%_Nightshift" /f >nul 2>&1
schtasks /delete /tn "%TASK_PREFIX%_Dayshift" /f >nul 2>&1
schtasks /delete /tn "%TASK_PREFIX%_Weekend" /f >nul 2>&1

:: Master scheduler - runs every 15 min, dispatches to correct mode based on ET time
schtasks /create /tn "%TASK_PREFIX%_Master" ^
    /tr "\"%PYTHON%\" \"%BASE%\master_shift_scheduler.py\"" ^
    /sc minute /mo 15 ^
    /ru "%USERNAME%" ^
    /f

echo.
echo ================================================
echo OuroTaurus Shift Automation Tasks Created
echo ================================================
echo.
echo Tasks:
echo   - %TASK_PREFIX%_Master     : every 15 min, dispatches mode based on ET time
echo   - Master script handles: dayshift, nightshift, crypto_weekend
echo.
echo Verify with: schtasks /query /fo list /v ^| findstr OuroTaurus_Shift
echo.
pause
