@echo off
setlocal
cd /d "%~dp0"

set "NGROK_URL=https://beula-nonintersecting-frigidly.ngrok-free.dev"
set "VERCEL_UI=https://mult-trade-forex.vercel.app"

echo ================================================================
echo  MulT - Dashboard + ngrok (static Dev Domain)
echo ================================================================
echo  Local:   http://localhost:8000
echo  Tunnel:  %NGROK_URL%
echo  Vercel:  %VERCEL_UI%?backend=%NGROK_URL%
echo ================================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] python not found in PATH.
  pause
  exit /b 1
)

where ngrok >nul 2>&1
if errorlevel 1 (
  echo [ERROR] ngrok not found in PATH.
  echo         Install: https://ngrok.com/download
  pause
  exit /b 1
)

echo Starting dashboard...
start "MulT Dashboard" cmd /k "cd /d ""%~dp0"" && python run_dashboard.py"

echo Waiting for dashboard on port 8000...
timeout /t 3 /nobreak >nul

echo Starting ngrok tunnel...
start "MulT ngrok" cmd /k "ngrok http 8000 --url %NGROK_URL%"

echo.
echo Done. Two windows opened:
echo   1. MulT Dashboard  - FastAPI on :8000
echo   2. MulT ngrok      - public tunnel
echo.
echo Open once in browser:
echo   %NGROK_URL%
echo   or
echo   %VERCEL_UI%?backend=%NGROK_URL%
echo.
pause
