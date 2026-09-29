@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m tvbakim %*
) else (
  python -m tvbakim %*
)
if errorlevel 1 pause
