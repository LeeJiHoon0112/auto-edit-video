@echo off
cd /d "%~dp0"
title PeiPei Auto Edit Video

echo  Dang mo PeiPei Auto Edit Video...

rem Mo app bang trinh chay Python KHONG console.
rem Uu tien pyw (luon co trong C:\Windows), roi pythonw, roi duong dan day du.
where pyw >nul 2>nul && (
  start "" pyw "%~dp0app.py"
  exit /b
)
where pythonw >nul 2>nul && (
  start "" pythonw "%~dp0app.py"
  exit /b
)
if exist "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe" (
  start "" "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe" "%~dp0app.py"
  exit /b
)

echo.
echo  [LOI] Khong tim thay Python (pyw/pythonw).
echo  Hay chay install.bat truoc, roi mo lai run.bat.
echo.
pause
