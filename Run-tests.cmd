@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" tools\run_tests.py
set result=%errorlevel%
pause
exit /b %result%
:missing
echo Run Setup.cmd first.
pause
exit /b 1
