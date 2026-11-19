@echo off
rem YKS Pusula - cift tikla calistir
rem PowerShell betik calistirma politikasi kapali olsa da calisir.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0baslat.ps1" %*
if errorlevel 1 pause
