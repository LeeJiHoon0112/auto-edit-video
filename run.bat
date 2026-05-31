@echo off
cd /d "%~dp0"
title Auto Edit Video

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  [LOI] Chua cai Python.
  echo  Hay bam vao  install.bat  truoc nhe, roi mo lai run.bat.
  echo.
  pause
  exit /b
)

echo  Dang mo Auto Edit Video...
start "" pythonw "%~dp0app.py"
