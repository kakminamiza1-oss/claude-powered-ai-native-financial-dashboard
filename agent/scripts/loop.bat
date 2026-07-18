@echo off
REM คลิกไฟล์นี้เพื่อเปิดแชท Local AI (free, no tokens) แบบหลายรอบ
REM หมายเหตุ: เครื่องนี้มี Device Guard บล็อก python.exe ของ venv
REM จึงใช้ "uv run python" (ผ่าน uv runtime) แทน
cd /d "%~dp0"
set "UV=%LOCALAPPDATA%\hermes\bin\uv.exe"
if not exist "%UV%" set "UV=uv"
"%UV%" run python local_chat.py --loop
pause
