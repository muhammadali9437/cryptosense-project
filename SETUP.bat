@echo off
title CryptoSense SETUP (run once)
echo ============================================
echo  CryptoSense SETUP - sirf pehli dafa chalana hai
echo ============================================
cd /d "%~dp0backend"
if not exist venv (
  python -m venv venv
) else (
  python -m venv --clear venv
)
call venv\Scripts\activate.bat
echo [1/3] Backend packages install ho rahe hain. Internet slow ho to intezar karein...
:retry
python -m pip install --default-timeout=1000 --retries 20 -r requirements.txt
if errorlevel 1 goto failed
goto ok
:failed
echo Internet toota. 5 second mein dobara koshish...
timeout /t 5 /nobreak >nul
goto retry
:ok
echo [2/3] Settings file bana raha hoon...
python make_env.py
cd /d "%~dp0frontend"
echo [3/3] Flutter app tayyar ho rahi hai...
if not exist web call flutter create . --platforms web
if exist test\widget_test.dart del test\widget_test.dart
call flutter pub get
echo.
echo ============================================
echo  SETUP MUKAMMAL! Ab START.bat par double click karein.
echo ============================================
pause
