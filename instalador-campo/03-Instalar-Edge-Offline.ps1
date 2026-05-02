param(
    [Parameter(Mandatory = $true)]
    [string]$OfflineBundle,
    [string]$Ingest,
    [string]$ClientId,
    [string]$CollectorKey,
    [switch]$Update
)

$ErrorActionPreference = "Stop"

$repoZip = "https://github.com/etitecnologies-sketch/ETI-SENTINEL/archive/refs/heads/main.zip"
$tmp = Join-Path $env:TEMP ("eti-sentinel-installer-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

try {
    $zip = Join-Path $tmp "main.zip"
    Write-Host "[INFO] Baixando instalador..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $repoZip -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $src = Get-ChildItem -Path $tmp -Directory | Where-Object { $_.Name -like "ETI-SENTINEL-*" } | Select-Object -First 1
    if (!$src) { throw "Falha ao extrair o repositório." }

    $setup = Join-Path $src.FullName "edge-installer\Setup-ETI-SENTINEL-Edge.ps1"
    if (!(Test-Path $setup)) { throw "Setup-ETI-SENTINEL-Edge.ps1 não encontrado no ZIP." }

    $args = @("-OfflineBundle", $OfflineBundle)
    if ($Ingest) { $args += @("-Ingest", $Ingest) }
    if ($ClientId) { $args += @("-ClientId", $ClientId) }
    if ($CollectorKey) { $args += @("-CollectorKey", $CollectorKey) }
    if ($Update) { $args += "-Update" }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup @args
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

