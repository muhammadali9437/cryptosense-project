@echo off
title CryptoSense - AI models train karein (optional)
cd /d "%~dp0backend"
call venv\Scripts\activate.bat
echo Binance se data le kar AI models train ho rahe hain (10 saal tak ka data, 15-30 minute)...
python -m ml.train --threshold 2.5
echo.
echo Train mukammal. Backend dobara START.bat se chalayein.
pause
