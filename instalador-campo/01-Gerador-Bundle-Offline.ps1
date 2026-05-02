param(
    [string]$OutDir = "./ETI-BUNDLE",
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

$repoZip = "https://github.com/etitecnologies-sketch/ETI-SENTINEL/archive/refs/heads/main.zip"
$tmp = Join-Path $env:TEMP ("eti-sentinel-bundle-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

try {
    $zipPath = Join-Path $tmp "main.zip"
    Write-Host "[INFO] Baixando scripts para gerar bundle..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $repoZip -OutFile $zipPath -UseBasicParsing
    Expand-Archive -Path $zipPath -DestinationPath $tmp -Force
    $src = Get-ChildItem -Path $tmp -Directory | Where-Object { $_.Name -like "ETI-SENTINEL-*" } | Select-Object -First 1
    if (!$src) { throw "Falha ao extrair o repositório." }

    $build = Join-Path $src.FullName "edge-installer\Build-OfflineBundle.ps1"
    if (!(Test-Path $build)) { throw "Build-OfflineBundle.ps1 não encontrado." }

    $args = @("-OutDir", $OutDir)
    if ($Zip) { $args += "-Zip" }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $build @args
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

