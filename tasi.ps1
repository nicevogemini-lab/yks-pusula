# A-KEY - ayri klasore / Google Drive'a tasima
#
#   Ornekler:
#     .\tasi.ps1 -Hedef "C:\Users\<kullanici>\Desktop"
#     .\tasi.ps1 -Hedef "G:\My Drive" -VeriyiTasi
#
#   Kaynak kopyalanir; .venv ve onbellek klasorleri TASINMAZ, cunku sanal ortam
#   mutlak yollar icerir. Hedefte bir kez .\baslat.ps1 calistirinca yeni sanal
#   ortam kurulur. -VeriyiTasi verilirse veri\pusula.db (tum ogrenci kayitlari)
#   da kopyalanir.
#
#   Not: Bu dosya bilincli olarak ASCII tutulmustur (Windows PowerShell 5.1
#        BOM'suz dosyalari ANSI okudugu icin Turkce karakterler bozulabilir).

param(
    [Parameter(Mandatory = $true)]
    [string]$Hedef,
    [switch]$VeriyiTasi
)

$ErrorActionPreference = "Stop"
$Kaynak = Split-Path -Parent $MyInvocation.MyCommand.Path
$HedefYol = Join-Path $Hedef "YKS-Pusula"

if (-not (Test-Path $Hedef)) {
    Write-Host "Hedef klasor yok: $Hedef" -ForegroundColor Red
    exit 1
}
if ((Resolve-Path $Hedef).Path -eq (Resolve-Path $Kaynak).Path) {
    Write-Host "Kaynak ve hedef ayni yer olamaz." -ForegroundColor Red
    exit 1
}
if (Test-Path $HedefYol) {
    Write-Host "Hedefte zaten bir YKS-Pusula klasoru var: $HedefYol" -ForegroundColor Yellow
    $onay = Read-Host "Uzerine yazilsin mi? (e/h)"
    if ($onay -ne "e") { exit 0 }
}

Write-Host "Kopyalaniyor: $Kaynak  ->  $HedefYol" -ForegroundColor Cyan

$haric = @("__pycache__", ".pytest_cache", ".venv", ".git")
if (-not $VeriyiTasi) { $haric += "veri" }

$argListe = @($Kaynak, $HedefYol, "/E", "/NFL", "/NDL", "/NJH", "/NJS")
foreach ($h in $haric) { $argListe += @("/XD", (Join-Path $Kaynak $h)) }

robocopy @argListe | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Host "Kopyalama basarisiz (robocopy kodu $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Kopyalama tamam: $HedefYol" -ForegroundColor Green
Write-Host "Sonraki adim:" -ForegroundColor Cyan
Write-Host "  1) $HedefYol klasorune gir"
Write-Host "  2) .\baslat.ps1 calistir (sanal ortami yeniden kurar)"
if (-not $VeriyiTasi) {
    Write-Host "  Not: Eski kayitlarin gerekli olursa -VeriyiTasi ile tekrar calistirabilirsin." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Google Drive icin: Google Drive for desktop'i kur, pano 'My Drive' klasorunu"
Write-Host "bu bilgisayara baglar. Sonra bu betigi -Hedef '<Drive>:\My Drive' ile calistir."
