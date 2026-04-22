@echo off
title Disk Kopyalama - Kurulum
color 0A
cd /d "%~dp0"

echo.
echo ========================================
echo   Disk Veri Kopyalama - Otomatik Kurulum
echo ========================================
echo.
echo Devam etmek icin bir tusa basin.
pause

echo.
echo [1/4] Python kontrol ediliyor...
where python >nul 2>nul
if %errorlevel% equ 0 goto PYBULUNDU
where py >nul 2>nul
if %errorlevel% equ 0 goto PYBULUNDU2
goto PYINDIR

:PYBULUNDU
echo [OK] Python mevcut.
set PYCMD=python
goto PIPDUR

:PYBULUNDU2
echo [OK] Python (py) mevcut.
set PYCMD=py
goto PIPDUR

:PYINDIR
echo [!] Python bulunamadi. Indiriliyor...
echo Lutfen bekleyin...
echo.
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '%TEMP%\python_setup.exe' -UseBasicParsing"

if not exist "%TEMP%\python_setup.exe" goto INDIRMEHATA
goto KURKISMI

:INDIRMEHATA
echo [HATA] Python indirilemedi! Internet kontrolu yapin.
pause
exit /b 1

:KURKISMI
echo [OK] Python indirildi.
echo Kurulum penceresi acilacak.
echo Add Python to PATH isaretleyin!
echo.
pause
start /wait "" "%TEMP%\python_setup.exe" PrependPath=1 Include_pip=1
del "%TEMP%\python_setup.exe" >nul 2>nul

echo.
echo Python kurulumu bitti mi? Devam icin tusa basin.
pause

set "PATH=C:\Program Files\Python312;C:\Program Files\Python312\Scripts;%PATH%"
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"

where python >nul 2>nul
if %errorlevel% equ 0 goto PYKURULDU
where py >nul 2>nul
if %errorlevel% equ 0 goto PYKURULDU2

echo [HATA] Python hala bulunamiyor.
echo PC yi yeniden baslatin ve tekrar deneyin.
pause
exit /b 1

:PYKURULDU
set PYCMD=python
echo [OK] Python kuruldu!
goto PIPDUR

:PYKURULDU2
set PYCMD=py
echo [OK] Python kuruldu!
goto PIPDUR

:PIPDUR
echo.
echo [2/4] pip guncelleniyor...
%PYCMD% -m pip install --upgrade pip >nul 2>nul
echo [OK] pip hazir.

echo.
echo [3/4] PyQt5 kontrol ediliyor...
%PYCMD% -c "import PyQt5" >nul 2>nul
if %errorlevel% equ 0 goto QT5VAR

echo PyQt5 kuruluyor (birkac dakika surebilir)...
%PYCMD% -m pip install PyQt5
if %errorlevel% neq 0 goto QT5HATA
echo [OK] PyQt5 kuruldu.
goto BASLAT

:QT5VAR
echo [OK] PyQt5 zaten kurulu.
goto BASLAT

:QT5HATA
echo [HATA] PyQt5 kurulamadi!
pause
exit /b 1

:BASLAT
echo.
echo [4/4] Uygulama baslatiliyor...
if not exist "%~dp0disk_copier.py" goto DOSYAYOK
echo Uygulama aciliyor...
start "" %PYCMD% "%~dp0disk_copier.py"
echo.
echo Uygulama baslatildi.
pause
exit /b 0

:DOSYAYOK
echo [HATA] disk_copier.py bulunamadi!
echo Bu bat ile ayni klasore koyun.
pause
exit /b 1
