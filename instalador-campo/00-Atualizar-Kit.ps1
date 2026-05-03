param(
    [string]$OutDir = "./KIT-PENDRIVE",
    [switch]$Zip,
    [switch]$WithOfflineBundle,
    [switch]$OfflineBundleZip
)

$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$p) {
    New-Item -ItemType Directory -Force -Path $p | Out-Null
}

$repoRoot = Split-Path -Parent $PSScriptRoot
if (!(Test-Path (Join-Path $repoRoot ".git"))) {
    throw "Este script deve ser executado dentro do repositório (com .git)."
}

Write-Host "[INFO] Atualizando repositório (git pull)..." -ForegroundColor Cyan
& git -C $repoRoot pull

$out = Join-Path $repoRoot $OutDir
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
Ensure-Dir $out

Write-Host "[INFO] Copiando pasta instalador-campo..." -ForegroundColor Cyan
Copy-Item -Path (Join-Path $repoRoot "instalador-campo") -Destination (Join-Path $out "instalador-campo") -Recurse -Force

if ($WithOfflineBundle) {
    Write-Host "[INFO] Gerando bundle offline..." -ForegroundColor Cyan
    $bundleDir = Join-Path $out "ETI-BUNDLE"
    $build = Join-Path $repoRoot "edge-installer\Build-OfflineBundle.ps1"
    if (!(Test-Path $build)) { throw "Build-OfflineBundle.ps1 não encontrado." }
    $args = @("-OutDir", $bundleDir)
    if ($OfflineBundleZip) { $args += "-Zip" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $build @args
}

if ($Zip) {
    $zipPath = ($out.TrimEnd("\\") + ".zip")
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Write-Host "[INFO] Gerando ZIP do kit: $zipPath" -ForegroundColor Cyan
    Compress-Archive -Path (Join-Path $out "*") -DestinationPath $zipPath -Force
}

Write-Host "[OK] Kit pronto em: $out" -ForegroundColor Green

