@echo off
REM Worker: รัน quick_brief.py (เร็ว < 2 นาที) เรียกโดย Windows Task Scheduler ทุก 08:00
REM ใช้ "uv run python" เพราะ Device Guard บล็อก python.exe ของ venv โดยตรง
cd /d "%~dp0"
set "UV=%LOCALAPPDATA%\hermes\bin\uv.exe"
if not exist "%UV%" set "UV=uv"
if exist telegram_config.bat call telegram_config.bat
set "LOG=%~dp0brief_log.txt"
echo ===== %date% %time% ===== >> "%LOG%"
"%UV%" run python "%~dp0quick_brief.py" >> "%LOG%" 2>&1
echo. >> "%LOG%"
