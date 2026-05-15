# ============================================================
#  ETI SENTINEL - Script de Download de Dependencias
#  Execute este script UMA VEZ para preparar a pasta bin/
#  antes de compilar o projeto.
#
#  Uso: Clique com botao direito > "Executar com PowerShell"
#       Ou: powershell -ExecutionPolicy Bypass -File .\baixar_dependencias.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$BinDir = Join-Path $PSScriptRoot "..\bin"

function Write-Step($msg) { Write-Host "`n  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  [ERRO] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Blue
Write-Host "    ETI SENTINEL - Baixando Dependencias" -ForegroundColor Blue
Write-Host "  ============================================================" -ForegroundColor Blue

# Cria a pasta bin/ se nao existir
if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
}
Write-Ok "Pasta bin/ pronta: $BinDir"

# ============================================================
#  FFMPEG
# ============================================================
Write-Step "[1/2] Baixando FFmpeg para Windows..."

$ffmpegDest = Join-Path $BinDir "ffmpeg.exe"

if (Test-Path $ffmpegDest) {
    Write-Ok "FFmpeg ja existe em bin\ — pulando."
} else {
    $downloaded = $false

    # Tenta via winget (Windows 11 / Windows 10 atualizado)
    Write-Host "  Tentando via winget..." -NoNewline
    try {
        $wg = Get-Command winget -ErrorAction SilentlyContinue
        if ($wg) {
            $tmp = Join-Path $env:TEMP "ffmpeg_winget"
            New-Item -ItemType Directory -Path $tmp -Force | Out-Null
            winget install --id Gyan.FFmpeg --source winget `
                --accept-package-agreements --accept-source-agreements `
                --location $tmp --silent 2>$null
            # Procura o ffmpeg.exe instalado
            $found = Get-ChildItem $tmp -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                Copy-Item $found.FullName $ffmpegDest
                $downloaded = $true
                Write-Host " OK"
            }
        }
    } catch { Write-Host " falhou" }

    # Fallback: download direto do repositorio oficial de builds Windows
    if (-not $downloaded) {
        Write-Host "  Baixando via download direto..." -NoNewline
        try {
            $zipUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            $zipTmp = Join-Path $env:TEMP "ffmpeg_essentials.zip"
            $extractTmp = Join-Path $env:TEMP "ffmpeg_extract"

            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $zipUrl -OutFile $zipTmp -UseBasicParsing
            Expand-Archive -Path $zipTmp -DestinationPath $extractTmp -Force
            $ffmpegExe = Get-ChildItem $extractTmp -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
            if ($ffmpegExe) {
                Copy-Item $ffmpegExe.FullName $ffmpegDest
                $downloaded = $true
                Write-Host " OK"
            }
            Remove-Item $zipTmp -Force -ErrorAction SilentlyContinue
            Remove-Item $extractTmp -Recurse -Force -ErrorAction SilentlyContinue
        } catch {
            Write-Host " falhou"
        }
    }

    if ($downloaded) {
        Write-Ok "FFmpeg salvo em: $ffmpegDest"
    } else {
        Write-Err "Nao foi possivel baixar o FFmpeg automaticamente."
        Write-Warn "Baixe manualmente em: https://www.gyan.dev/ffmpeg/builds/"
        Write-Warn "Copie o ffmpeg.exe para: $BinDir"
    }
}

# ============================================================
#  NSSM (gerenciador de servicos Windows)
# ============================================================
Write-Step "[2/2] Baixando NSSM..."

$nssmDest = Join-Path $BinDir "nssm.exe"

if (Test-Path $nssmDest) {
    Write-Ok "NSSM ja existe em bin\ — pulando."
} else {
    try {
        $nssmUrl = "https://nssm.cc/release/nssm-2.24.zip"
        $nssmZip = Join-Path $env:TEMP "nssm.zip"
        $nssmExtract = Join-Path $env:TEMP "nssm_extract"

        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $nssmUrl -OutFile $nssmZip -UseBasicParsing
        Expand-Archive -Path $nssmZip -DestinationPath $nssmExtract -Force

        # Pega o nssm.exe de 64 bits
        $nssmExe = Get-ChildItem $nssmExtract -Recurse -Filter "nssm.exe" |
            Where-Object { $_.FullName -like "*win64*" } | Select-Object -First 1

        if (-not $nssmExe) {
            $nssmExe = Get-ChildItem $nssmExtract -Recurse -Filter "nssm.exe" | Select-Object -First 1
        }

        if ($nssmExe) {
            Copy-Item $nssmExe.FullName $nssmDest
            Write-Ok "NSSM salvo em: $nssmDest"
        } else {
            Write-Err "nssm.exe nao encontrado no zip."
        }
        Remove-Item $nssmZip -Force -ErrorAction SilentlyContinue
        Remove-Item $nssmExtract -Recurse -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Err "Nao foi possivel baixar o NSSM: $_"
        Write-Warn "Baixe manualmente em: https://nssm.cc/download"
        Write-Warn "Copie o nssm.exe (win64) para: $BinDir"
    }
}

# ============================================================
#  [3/3] MODELO DE IA (ONNX)
# ============================================================
Write-Step "[3/3] Verificando modelo de IA (ONNX)..."

$modelDest = Join-Path $BinDir "modelo_ia.onnx"
$exportScript = Join-Path $PSScriptRoot "..\exportar_modelo.py"

if (Test-Path $modelDest) {
    $sizeMB = [math]::Round((Get-Item $modelDest).Length / 1MB, 1)
    Write-Ok "Modelo IA ja existe: modelo_ia.onnx ($sizeMB MB) — pulando."
} elseif (Test-Path $exportScript) {
    Write-Host "  Exportando modelo YOLOv8n para ONNX (requer internet)..." -NoNewline
    try {
        $python = (Get-Command python -ErrorAction Stop).Source
        & $python $exportScript --model yolov8n 2>$null
        if (Test-Path $modelDest) {
            Write-Host " OK"
            Write-Ok "Modelo exportado: $modelDest"
        } else {
            Write-Host " falhou"
            Write-Warn "Execute manualmente: python exportar_modelo.py"
        }
    } catch {
        Write-Host " sem Python"
        Write-Warn "Execute depois: python exportar_modelo.py"
    }
} else {
    Write-Warn "exportar_modelo.py nao encontrado. Execute: python exportar_modelo.py"
}

# ============================================================
#  RESUMO FINAL
# ============================================================
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Blue
Write-Host "    Conteudo atual da pasta bin/" -ForegroundColor Blue
Write-Host "  ============================================================" -ForegroundColor Blue
Get-ChildItem $BinDir | ForEach-Object {
    $size = [math]::Round($_.Length / 1MB, 1)
    Write-Host "    $($_.Name) ($size MB)"
}
Write-Host ""
Write-Host "  Proximo passo: execute  python build_exe.py  para compilar." -ForegroundColor Green
Write-Host ""
