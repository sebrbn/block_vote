@echo off
title BlockVote Admin Node Setup
echo ==========================================
echo    Secure Voting System - Admin Node
echo ==========================================
echo.

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3 and add it to PATH.
    pause
    exit /b
)

echo [*] Installing dependencies...
pip install -r requirements.txt

echo.
set /p PORT="Enter Port number (default 5000): "
if "%PORT%"=="" set PORT=5000

set /p TOKEN="Enter Admin Secret Token (default: admin-secret-123): "
if "%TOKEN%"=="" set TOKEN=admin-secret-123

echo.
echo [*] Starting node on port %PORT% with security token enabled...
set ADMIN_TOKEN=%TOKEN%
python app.py -p %PORT%

pause
