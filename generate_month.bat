@echo off
rem Generates last month's reports for every instance in config.toml.
rem Can be scheduled with Windows Task Scheduler.
cd /d "%~dp0"
python generate_month.py %*
echo.
pause
