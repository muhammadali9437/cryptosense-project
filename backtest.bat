@echo off
title CryptoSense - Backtest (AI results CSV mein)
cd /d "%~dp0backend"
if not exist venv\Scripts\python.exe (
  echo venv nahi mila. Pehle SETUP.bat chalayein.
  pause
  exit /b 1
)
call venv\Scripts\activate.bat
set DAYS=90
set /p DAYS=Kitne din ka test karna hai? (Enter = 90):
echo Binance se pichle %DAYS% din ka data le kar AI ko test kiya ja raha hai...
python -m ml.backtest --days %DAYS%
if errorlevel 1 (
  echo.
  echo BACKTEST FAIL HUA. Upar wala error dekhein.
  pause
  exit /b 1
)
echo.
echo Results folder khul raha hai...
start "" "%~dp0backend\ml\backtest_results"
pause