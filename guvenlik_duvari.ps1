# YKS Pusula - telefondan/tabletten erisim icin guvenlik duvari kurali
#   Kullanim: sag tik -> "Yonetici olarak calistir"   (veya .\guvenlik_duvari.ps1)
#   Ne yapar: 8317 portunu yalnizca ayni agdaki cihazlara (LocalSubnet) acar.
#   Not: Bu dosya bilincli olarak ASCII tutulmustur (Windows PowerShell 5.1
#        BOM'suz dosyalari ANSI okudugu icin Turkce karakterler bozulabilir).

$ErrorActionPreference = "Stop"
$Ad = "YKS Pusula 8317 (yerel ag)"

$yonetici = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $yonetici) {
    Write-Host "Yonetici izni isteniyor; cikan pencerede 'Evet' sec..." -ForegroundColor Yellow
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`""
    )
    exit
}

Get-NetFirewallRule -DisplayName $Ad -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule `
    -DisplayName $Ad `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort 8317 `
    -Action Allow `
    -Profile Private, Public `
    -RemoteAddress LocalSubnet `
    -Description "Ayni Wi-Fi agindaki telefon/tablet YKS Pusula'ya baglanabilsin" | Out-Null

Write-Host "Kural eklendi: $Ad" -ForegroundColor Green

# Ayni agdaki cihazlarin kullanacagi adres
$ip = "127.0.0.1"
try {
    $soket = New-Object System.Net.Sockets.Socket(
        [System.Net.Sockets.AddressFamily]::InterNetwork,
        [System.Net.Sockets.SocketType]::Dgram,
        [System.Net.Sockets.ProtocolType]::Udp)
    $soket.Connect("8.8.8.8", 80)
    $ip = $soket.LocalEndPoint.Address.ToString()
    $soket.Close()
} catch { }

Write-Host ""
Write-Host "Telefondan acilacak adres: http://${ip}:8317" -ForegroundColor Cyan
Write-Host "Telefon da bilgisayarla ayni Wi-Fi aginda olmali." -ForegroundColor Cyan
Write-Host "Sunucu kapaliysa once baslat.cmd dosyasini calistir." -ForegroundColor Cyan
Write-Host ""
Read-Host "Kapatmak icin Enter"
