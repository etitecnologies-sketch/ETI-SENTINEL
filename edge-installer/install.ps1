$url = "https://raw.githubusercontent.com/etitecnologies-sketch/ETI-SENTINEL/main/edge-installer/Setup-ETI-SENTINEL-Edge.ps1"
$tmp = Join-Path $env:TEMP "Setup-ETI-SENTINEL-Edge.ps1"
Write-Host "[INFO] Baixando instalador ETI SENTINEL..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
powershell.exe -ExecutionPolicy Bypass -File $tmp
