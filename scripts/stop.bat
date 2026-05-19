@echo off
setlocal

if /i "%~1"=="/silent" set "NO_PAUSE=1"

set "PORT=8765"
set "FOUND=0"

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
  echo Stopping PID %%P on port %PORT%...
  taskkill /F /PID %%P >nul 2>&1
  set "FOUND=1"
)

taskkill /F /FI "WINDOWTITLE eq Yukti - Voice Assistant*" >nul 2>&1

if "%FOUND%"=="1" (
  echo Done. Server stopped.
) else (
  echo No server found on port %PORT%.
)

echo.
if not defined NO_PAUSE pause
endlocal
