@echo off
setlocal
cd /d "%~dp0\.."

set "PORT=8765"
set "URL=http://127.0.0.1:%PORT%/"
set "PY=%CD%\.venv\Scripts\python.exe"
set "PYTHONPATH=%CD%\src"

echo ========================================
echo   Yukti Voice Assistant - Start
echo ========================================
echo.

call "%~dp0stop.bat" /silent >nul 2>&1

if not exist "%PY%" (
  echo [1/3] Creating virtual environment...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo ERROR: Could not create .venv. Install Python 3.12+ and try again.
    pause
    exit /b 1
  )
)

if not exist ".venv\Scripts\uvicorn.exe" (
  echo [2/3] Installing dependencies (first run may take a few minutes)...
  "%PY%" -m pip install -q --upgrade pip
  "%PY%" -m pip install -q -r requirements.txt
  if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
  )
) else (
  echo [2/3] Dependencies OK
)

if not exist ".env" (
  echo.
  echo WARNING: .env not found. Copy .env.example to .env and set GROQ_API_KEY.
  echo.
)

echo [3/3] Starting server on %URL%
start "Yukti - Voice Assistant" cmd /k "set PYTHONPATH=%CD%\src&& "%PY%" -m uvicorn yukti.api.app:app --host 127.0.0.1 --port %PORT% --reload"

timeout /t 3 /nobreak >nul
start "" "%URL%"

echo.
echo Server started in a separate window.
echo Open %URL% if the browser did not launch.
echo Run scripts\stop.bat to shut down.
echo.
pause
endlocal
