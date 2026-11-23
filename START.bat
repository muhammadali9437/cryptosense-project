@echo off
setlocal
title CryptoSense START

if not exist "%~dp0backend\venv\Scripts\python.exe" (
  echo Backend setup is missing. Run SETUP.bat first.
  pause
  exit /b 1
)

where flutter >nul 2>nul
if errorlevel 1 (
  echo Flutter was not found on PATH. Add Flutter's bin folder to PATH, then try again.
  pause
  exit /b 1
)

echo Starting the backend...
start "CryptoSense Backend" /D "%~dp0backend" cmd /k "call venv\Scripts\activate.bat && python -m uvicorn app.main:app --reload"

echo Waiting for the backend to become ready...
set /a attempts=0
:wait_backend
"%~dp0backend\venv\Scripts\python.exe" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2).close()" >nul 2>nul
if not errorlevel 1 goto backend_ready
set /a attempts+=1
if %attempts% geq 30 goto backend_failed
timeout /t 2 /nobreak >nul
goto wait_backend

:backend_ready
echo Backend is ready at http://127.0.0.1:8000/docs
echo Starting Flutter. Its first Chrome launch can take a minute.
start "CryptoSense Frontend" /D "%~dp0frontend" cmd /k "flutter run -d chrome"
echo Frontend is starting in its own window. Wait there for Chrome to open.
echo To stop both services, press Ctrl+C in each service window.
exit /b 0

:backend_failed
echo Backend did not respond within 60 seconds. Check the CryptoSense Backend window for its error.
pause
exit /b 1
