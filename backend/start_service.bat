@echo off
chcp 65001 >nul
REM openshortvideo startup script (Windows)

echo ========================================
echo     Starting openshortvideo...
echo ========================================

REM Change to backend directory
cd /d "%~dp0backend"

REM Set UTF-8 encoding mode for Python
set PYTHONUTF8=1

REM Start application
echo Starting application...
python  app_service.py
pause