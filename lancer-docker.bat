@echo off
cd /d "%~dp0"

set "DOCKER=docker"
where docker >nul 2>&1
if errorlevel 1 (
  if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" (
    set "DOCKER=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
  ) else if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    echo Start Docker Desktop, wait until it is running, then run this file again.
    pause
    exit /b 1
  ) else (
    echo Docker was not found. Install Docker Desktop and start it first.
    pause
    exit /b 1
  )
)

echo Building images and starting MySQL + the app...
"%DOCKER%" compose up --build
pause
