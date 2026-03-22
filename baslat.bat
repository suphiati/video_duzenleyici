@echo off
title Video Duzenleyici
cd /d "%~dp0"
echo Video Duzenleyici baslatiliyor...
echo Tarayicide http://localhost:8000 adresini acin
echo Kapatmak icin bu pencereyi kapatin.
echo.
start http://localhost:8000
python run.py
