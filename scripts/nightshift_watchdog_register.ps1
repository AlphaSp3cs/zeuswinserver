$action = New-ScheduledTaskAction -Execute 'C:\Users\bravo-usr1\AppData\Local\Microsoft\WindowsApps\python3.exe' -Argument '"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\scripts\nightshift_watchdog.py"'
$trigger = New-ScheduledTaskTrigger -Once -At 18:01 -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Hours 15)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName 'OuroTaurus_Nightshift_Watchdog' -Action $action -Trigger $trigger -Settings $settings -User 'bravo-usr1' -Force
