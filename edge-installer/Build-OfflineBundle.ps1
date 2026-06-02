param(
    [string]$OutDir = "./edge-installer-bundle",
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

# ── VERSÕES DE DEPENDÊNCIAS ─────────────────────────────
# Para atualizar uma dependência, altere apenas aqui.
$DEP = @{
    PythonVersion   = "3.12.10"
    PythonUrl       = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    WinswVersion    = "2.12.0"
    WinswUrl        = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
    MediamtxVersion = "1.9.0"
    MediamtxUrl     = "https://github.com/bluenviron/mediamtx/releases/download/v1.9.0/mediamtx_v1.9.0_windows_amd64.zip"
    FfmpegUrl       = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
}
# ────────────────────────────────────────────────────────

# Hashes SHA256 conhecidos — atualize a cada nova versão das dependências.
# Para obter o hash: (Get-FileHash <arquivo> -Algorithm SHA256).Hash
$KNOWN_HASHES = @{
    "winsw"    = "05B82D46AD331CC16BDC00DE5C6332C1EF818DF8CEEFCD49C726553209B3A0DA"
    "python"   = "67B5635E80EA51072B87941312D00EC8927C4DB9BA18938F7AD2D27B328B95FB"
    "mediamtx" = "2279B921B2BFB69321A142090DB0AC88A36AB2093AFBB9F5A59ECA94BE0C03FA"
    # ffmpeg: hash não disponível publicamente — verificação pulada, mas registrada no manifest
}

function Ensure-Dir([string]$p) {
    New-Item -ItemType Directory -Force -Path $p | Out-Null
}

function Dl([string]$url, [string]$dest, [string]$ExpectedSha256 = "") {
    Write-Host "[INFO] Download: $url" -ForegroundColor Cyan
    Ensure-Dir (Split-Path -Parent $dest)
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    if (!(Test-Path $dest)) { throw "download_failed: $url" }

    # Verifica integridade se hash foi fornecido e não é placeholder
    if ($ExpectedSha256 -and $ExpectedSha256 -notlike "SHA256_*") {
        $actual = (Get-FileHash $dest -Algorithm SHA256).Hash
        if ($actual -ne $ExpectedSha256) {
            Remove-Item $dest -Force -ErrorAction SilentlyContinue
            throw "Hash inválido para $url. Arquivo pode estar corrompido ou adulterado."
        }
        Write-Host "[OK] Hash verificado: $([System.IO.Path]::GetFileName($dest))" -ForegroundColor Green
    }
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

Dl $DEP.WinswUrl    (Join-Path $root "winsw\WinSW-x64.exe")                                          $KNOWN_HASHES["winsw"]
Dl $DEP.PythonUrl   (Join-Path $root "python\python-$($DEP.PythonVersion)-amd64.exe")                $KNOWN_HASHES["python"]
Dl $DEP.FfmpegUrl   (Join-Path $root "ffmpeg\ffmpeg-release-essentials.zip")
Dl $DEP.MediamtxUrl (Join-Path $root "mediamtx\mediamtx_v$($DEP.MediamtxVersion)_windows_amd64.zip") $KNOWN_HASHES["mediamtx"]
Dl "https://github.com/etitecnologies-sketch/ETI-SENTINEL/archive/refs/heads/main.zip" (Join-Path $root "repo\main.zip")

try {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $req   = Join-Path $repoRoot "edge-agent\requirements.txt"
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

# Calcula hashes reais de todos os arquivos e gera manifest.json para rastreabilidade
Write-Host "[INFO] Gerando manifest.json do bundle..." -ForegroundColor Cyan
$filesHashes = @{}
Get-ChildItem -Path $root -Recurse -File | ForEach-Object {
    $relPath = $_.FullName.Substring($root.Length).TrimStart("\")
    $filesHashes[$relPath] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
}
$manifest = @{
    bundle_version   = "2.1"
    build_date       = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    python_version   = $DEP.PythonVersion
    winsw_version    = $DEP.WinswVersion
    mediamtx_version = $DEP.MediamtxVersion
    files            = $filesHashes
}
$manifest | ConvertTo-Json -Depth 5 | Out-File (Join-Path $root "manifest.json") -Encoding UTF8

if ($Zip) {
    $zipPath = ($root.TrimEnd("\\") + ".zip")
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Write-Host "[INFO] Gerando ZIP: $zipPath" -ForegroundColor Cyan
    Compress-Archive -Path (Join-Path $root "*") -DestinationPath $zipPath -Force
}

Write-Host "[OK] Bundle gerado em: $root" -ForegroundColor Green
