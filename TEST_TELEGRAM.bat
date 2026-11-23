@echo off
setlocal
title CryptoSense Telegram Test

if not exist "%~dp0backend\venv\Scripts\python.exe" (
  echo Backend setup is missing. Run SETUP.bat first.
  pause
  exit /b 1
)

pushd "%~dp0backend"
venv\Scripts\python.exe -m app.test_telegram
set result=%errorlevel%
popd

if not "%result%"=="0" echo Telegram test did not complete successfully.
pause
exit /b %result%
