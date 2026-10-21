@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" app.py %*
if errorlevel 1 pause
exit /b
:missing
echo Run Setup.cmd first to install the source edition.
pause
exit /b 1
