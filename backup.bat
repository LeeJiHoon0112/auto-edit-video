@echo off
cd /d "%~dp0"
title Backup PeiPei Auto Edit Video
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0backup.ps1"
echo.
pause
