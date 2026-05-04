param(
    [string]$OutDir = "./edge-installer-bundle",
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$p) {
    New-Item -ItemType Directory -Force -Path $p | Out-Null
}

function Dl([string]$url, [string]$dest) {
    Write-Host "[INFO] Download: $url" -ForegroundColor Cyan
    Ensure-Dir (Split-Path -Parent $dest)
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    if (!(Test-Path $dest)) { throw "download_failed: $url" }
}

$outRaw = $OutDir
if (!$outRaw) { $outRaw = "./edge-installer-bundle" }
Ensure-Dir $outRaw
$root = (Resolve-Path $outRaw).Path
Ensure-Dir (Join-Path $root "winsw")
Ensure-Dir (Join-Path $root "python")
Ensure-Dir (Join-Path $root "ffmpeg")
Ensure-Dir (Join-Path $root "mediamtx")
Ensure-Dir (Join-Path $root "wheelhouse")
Ensure-Dir (Join-Path $root "repo")

Dl "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe" (Join-Path $root "winsw\WinSW-x64.exe")
Dl "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" (Join-Path $root "python\python-3.12.10-amd64.exe")
Dl "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" (Join-Path $root "ffmpeg\ffmpeg-release-essentials.zip")
Dl "https://github.com/bluenviron/mediamtx/releases/download/v1.9.0/mediamtx_v1.9.0_windows_amd64.zip" (Join-Path $root "mediamtx\mediamtx_v1.9.0_windows_amd64.zip")
Dl "https://github.com/etitecnologies-sketch/ETI-SENTINEL/archive/refs/heads/main.zip" (Join-Path $root "repo\main.zip")

try {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $req = Join-Path $repoRoot "edge-agent\requirements.txt"
    $reqAi = Join-Path $repoRoot "edge-agent\requirements-ai.txt"
    if (Test-Path $req) {
        Write-Host "[INFO] Baixando wheels (wheelhouse) a partir de requirements.txt" -ForegroundColor Cyan
        $wh = (Join-Path $root "wheelhouse")
        $pipDownload = @("-m","pip","download","--dest",$wh,"--only-binary=:all:","--platform","win_amd64","--python-version","312","--implementation","cp","--abi","cp312")
        python @pipDownload "pip" "setuptools" "wheel" "build"
        python @pipDownload "-r" $req
    } else {
        Write-Host "[WARN] requirements.txt não encontrado; pulando wheelhouse" -ForegroundColor Yellow
    }
    if (Test-Path $reqAi) {
        Write-Host "[INFO] Baixando wheels (wheelhouse) a partir de requirements-ai.txt" -ForegroundColor Cyan
        $wh = (Join-Path $root "wheelhouse")
        $pipDownload = @("-m","pip","download","--dest",$wh,"--only-binary=:all:","--platform","win_amd64","--python-version","312","--implementation","cp","--abi","cp312")
        python @pipDownload "-r" $reqAi
    }
} catch {
    Write-Host "[WARN] Falha ao baixar wheelhouse automaticamente: $($_.Exception.Message)" -ForegroundColor Yellow
}

if ($Zip) {
    $zipPath = ($root.TrimEnd("\\") + ".zip")
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Write-Host "[INFO] Gerando ZIP: $zipPath" -ForegroundColor Cyan
    Compress-Archive -Path (Join-Path $root "*") -DestinationPath $zipPath -Force
}

Write-Host "[OK] Bundle gerado em: $root" -ForegroundColor Green
