@echo off
cd /d "%~dp0"
title Cap nhat PeiPei Auto Edit Video
echo.
echo  ============================================
echo      CAP NHAT PEIPEI AUTO EDIT VIDEO
echo  ============================================
echo.

REM --- Kiem tra Git da cai chua ---
where git >nul 2>nul
if errorlevel 1 (
  echo  [LOI] May ban chua cai Git.
  echo  Hay tai va cai Git tai: https://git-scm.com/download/win
  echo  Sau do mo lai file nay.
  echo.
  pause
  exit /b
)

REM --- Kiem tra co phai thu muc git clone khong ---
if not exist ".git" (
  echo  [LOI] Thu muc nay khong phai ban tai bang "git clone".
  echo  Hay tai lai dung cach bang lenh:
  echo.
  echo     git clone https://github.com/LeeJiHoon0112/auto-edit-video.git
  echo.
  pause
  exit /b
)

REM --- Keo ban moi nhat ve ---
echo  Dang kiem tra ban cap nhat tren GitHub...
echo.
git pull --ff-only
set ERR=%errorlevel%
echo.
if %ERR%==0 (
  echo  [OK] Hoan tat - ban dang dung phien ban MOI NHAT.
) else (
  echo  [CHU Y] Khong tu cap nhat duoc.
  echo          Co the do ban da chinh sua file code trong thu muc.
  echo          Hay sao luu thay doi rieng ra cho khac roi mo lai file nay.
)
echo.
echo  Phien ban hien tai:
git log -1 --format="    %%h  -  %%s  (%%cd)" --date=short
echo.
echo  ============================================
pause
