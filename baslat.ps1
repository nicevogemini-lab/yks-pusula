# YKS Pusula - tek tik baslatici
#   Ilk calistirmada sanal ortami kurar, sonraki calistirmalarda dogrudan acar.
#   Kullanim: sag tik -> "PowerShell ile calistir"  veya  .\baslat.ps1
#   Not: Bu dosya bilincli olarak ASCII tutulmustur (Windows PowerShell 5.1
#        BOM'suz dosyalari ANSI okudugu icin Turkce karakterler bozulabilir).

$ErrorActionPreference = "Stop"
$Kok = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Kok

$Venv = Join-Path $Kok ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "Ilk kurulum yapiliyor, birkac dakika surebilir..." -ForegroundColor Cyan

    $SistemPy = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $SistemPy) { $SistemPy = (Get-Command py -ErrorAction SilentlyContinue).Source }
    if (-not $SistemPy) {
        Write-Host "Python bulunamadi. https://www.python.org/downloads/ adresinden kurup tekrar dene." -ForegroundColor Red
        Read-Host "Kapatmak icin Enter"
        exit 1
    }

    & $SistemPy -m venv $Venv
    & $Py -m pip install --upgrade pip --quiet
    & $Py -m pip install -r (Join-Path $Kok "requirements.txt")
    Write-Host "Kurulum tamam." -ForegroundColor Green
}

if (-not (Test-Path (Join-Path $Kok ".env"))) {
    Copy-Item (Join-Path $Kok ".env.example") (Join-Path $Kok ".env")
    Write-Host ".env olusturuldu (.env.example kopyalandi)." -ForegroundColor Yellow
}

& $Py (Join-Path $Kok "baslat.py") @args
