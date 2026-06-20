@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo  BUILD PeiPei Auto Edit Video - dong goi 1 file .exe bang Nuitka
echo  An toan: .exe KHONG kem config.local.json / access.json /
echo  session.local.json (API key + license may ban).
echo ============================================================
echo.

REM --- Chan ban ban phai BAT license ---
findstr /C:"LICENSE_ENABLED = True" config.py >nul
if errorlevel 1 goto :notenabled
echo [OK] config.py LICENSE_ENABLED = True.
echo.

echo [1/2] Cai/cap nhat cong cu build + thu vien license...
python -m pip install --upgrade nuitka requests cryptography certifi
echo.

echo [2/2] Build .exe (lan dau co the tai trinh bien dich vai phut)...
python -m nuitka --standalone --onefile --enable-plugin=tk-inter --include-package=cryptography --include-package=certifi --windows-console-mode=disable --assume-yes-for-downloads --remove-output --output-dir=release --output-filename=AutoEditVideo.exe app.py
echo.

if exist "release\AutoEditVideo.exe" goto :done
echo  !! Build that bai - xem loi o tren.
goto :end

:notenabled
echo  !! config.py dang LICENSE_ENABLED = False.
echo  Mo config.py sua thanh:  LICENSE_ENABLED = True  roi chay lai build nay.
goto :end

:done
echo Copy ffmpeg + ffprobe vao release (de khach KHOI CAI ffmpeg)...
python -c "import auto_edit,shutil; ff=auto_edit.find_tool('ffmpeg'); fp=auto_edit.find_tool('ffprobe'); (shutil.copy(ff,'release') if ff else None); (shutil.copy(fp,'release') if fp else None); print('  ffmpeg :',ff); print('  ffprobe:',fp)"
echo.
echo XONG! Giao cho khach CA THU MUC release\ (AutoEditVideo.exe + ffmpeg.exe + ffprobe.exe).
echo Giao kem: docs\HUONG_DAN_SU_DUNG.txt + license key (tao o admin, product = aev).
echo TUYET DOI KHONG giao kem config.local.json - file do chua API key cua ban.

:end
pause
