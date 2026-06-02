param([string]$Version = "v2.1")

# Substitua pelo hash SHA256 real do Setup-ETI-SENTINEL-Edge.ps1 de cada release.
# Para obter: (Get-FileHash .\Setup-ETI-SENTINEL-Edge.ps1 -Algorithm SHA256).Hash
$EXPECTED_SHA256 = "FAEA4F51EC50DB8E64971C0EE7B197BA86F2DC13C7086DD6AAC01DC315D55679"
$url = "https://github.com/etitecnologies-sketch/ETI-SENTINEL/releases/download/$Version/Setup-ETI-SENTINEL-Edge.ps1"
$tmp = Join-Path $env:TEMP "Setup-ETI-SENTINEL-Edge.ps1"

try {
    Write-Host "[INFO] Baixando instalador ETI SENTINEL $Version..." -ForegroundColor Cyan
    $resp = Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing -PassThru
    if ($resp.StatusCode -ne 200) { throw "HTTP $($resp.StatusCode)" }

    $actualHash = (Get-FileHash $tmp -Algorithm SHA256).Hash
    if ($actualHash -ne $EXPECTED_SHA256) {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
        throw "Hash inválido. Arquivo pode estar corrompido ou adulterado. Abortando."
    }

    Write-Host "[OK] Integridade verificada." -ForegroundColor Green
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File $tmp -Version $Version
} catch {
    Write-Host "[ERR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}
