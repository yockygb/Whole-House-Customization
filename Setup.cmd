@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 goto usepython
py -3 -m venv .venv
if errorlevel 1 goto failed
goto install
:usepython
where python >nul 2>nul
if errorlevel 1 goto missing
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ required'"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Setup complete. Double-click Start.cmd to launch.
pause
exit /b 0
:missing
echo Install Python 3.11 or newer from https://www.python.org/downloads/windows/ then run Setup.cmd again.
pause
exit /b 1
:failed
echo Setup failed. Review the error above.
pause
exit /b 1
