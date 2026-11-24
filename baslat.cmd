@echo off
rem A-KEY - cift tikla calistir
rem PowerShell betik calistirma politikasi kapali olsa da calisir.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0baslat.ps1" %*
if errorlevel 1 pause
