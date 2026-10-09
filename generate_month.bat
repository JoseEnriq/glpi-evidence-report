@echo off
rem Generates last month's reports for every instance in config.toml.
rem   Double-click:   waits for a key at the end, so the output can be read.
rem   Task Scheduler: pass the argument --scheduled (no pause; the exit code
rem                   is returned, so a failed run shows up as an error).
cd /d "%~dp0"
if /i "%~1"=="--scheduled" goto scheduled
python generate_month.py %*
set "RC=%ERRORLEVEL%"
echo.
pause
exit /b %RC%

:scheduled
python generate_month.py
exit /b %ERRORLEVEL%
