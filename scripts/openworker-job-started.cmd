@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "C:\ProgramData\OpenWorker\hooks\openworker-job-started-hook.ps1"
exit /b %ERRORLEVEL%
