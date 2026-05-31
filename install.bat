@echo off
cd /d "%~dp0"
title Cai dat Auto Edit Video
echo.
echo  ==============================================
echo       CAI DAT AUTO EDIT VIDEO
echo  ==============================================
echo.
echo  File nay se kiem tra va cai: Python va FFmpeg.
echo.

set HASWINGET=1
where winget >nul 2>nul
if errorlevel 1 set HASWINGET=0

REM ---------- 1) Python ----------
echo  [1/3] Kiem tra Python...
where python >nul 2>nul
if %errorlevel%==0 (
  echo        Python: DA CO
) else (
  if "%HASWINGET%"=="1" (
    echo        Chua co - dang cai bang winget, vui long cho...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo.
    echo        ^>^> Da cai Python. Hay DONG cua so nay va MO LAI install.bat de tiep tuc.
    echo.
    pause
    exit /b
  ) else (
    echo        [LOI] Chua co Python va may khong co winget.
    echo        Hay tai Python tai: https://www.python.org/downloads/
    echo        Khi cai NHO TICH o "Add Python to PATH".
    echo.
    pause
    exit /b
  )
)

REM ---------- 2) FFmpeg ----------
echo  [2/3] Kiem tra FFmpeg...
where ffmpeg >nul 2>nul
if %errorlevel%==0 (
  echo        FFmpeg: DA CO
) else (
  if "%HASWINGET%"=="1" (
    echo        Chua co - dang cai bang winget, vui long cho...
    winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    echo        FFmpeg da cai ^(tool tu tim, khong can chinh PATH^).
  ) else (
    echo        [CHU Y] Chua co FFmpeg va khong co winget.
    echo        Hay tai FFmpeg tai: https://www.gyan.dev/ffmpeg/builds/
  )
)

REM ---------- 3) Thu vien Python ----------
echo  [3/3] Cai thu vien Python ^(neu can^)...
python -m pip install -r requirements.txt --quiet

echo.
echo  ==============================================
echo   CAI DAT XONG! Bay gio bam vao  run.bat  de mo app.
echo  ==============================================
echo.
pause
