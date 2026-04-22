@echo off
title Disk Veri Kopyalama Araci
cd /d "%~dp0"

:: Python kontrolu
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Python bulunamadi! Lutfen Python yukleyin.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)

:: PyQt5 kontrolu ve kurulumu
python -c "import PyQt5" >nul 2>&1
if %errorlevel% neq 0 (
    echo PyQt5 kuruluyor...
    pip install PyQt5
)

:: Programi baslat
python disk_copier.py
pause
