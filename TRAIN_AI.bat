@echo off
title CryptoSense - AI models train karein (optional)
cd /d "%~dp0backend"
call venv\Scripts\activate.bat
echo Binance se data le kar AI models train ho rahe hain (10-20 minute)...
python -m ml.train --no-gru
echo.
echo Train mukammal. Backend dobara START.bat se chalayein.
pause
