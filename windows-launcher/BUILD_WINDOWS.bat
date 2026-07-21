@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer from python.org.
  exit /b 1
)

py -3 -m pip install --upgrade pip
if errorlevel 1 exit /b 1
py -3 -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name "BigShot Business OS" BigShotBusinessOS.py
if errorlevel 1 exit /b 1

copy /Y "dist\BigShot Business OS.exe" ".\BigShot Business OS.exe" >nul
echo.
echo Build complete: %CD%\BigShot Business OS.exe
endlocal
