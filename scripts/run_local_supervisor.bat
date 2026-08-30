@echo off
setlocal
cd /d "%~dp0\.."
if "%OPENWORKER_LOCAL_SUPERVISOR_CONFIG%"=="" set "OPENWORKER_LOCAL_SUPERVISOR_CONFIG=config\local_supervisor.example.toml"
python -m coworker.local_supervisor --config "%OPENWORKER_LOCAL_SUPERVISOR_CONFIG%" %*
endlocal
