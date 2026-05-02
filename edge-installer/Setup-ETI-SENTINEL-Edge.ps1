param(
    [string]$Ingest,
    [string]$CollectorKey,
    [string]$ClientId,
    [switch]$Update
)

$ErrorActionPreference = "Stop"

try {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
} catch {}

function Write-Ok([string]$m) { Write-Host "[OK]  $m" -ForegroundColor Green }
function Write-Inf([string]$m) { Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Wrn([string]$m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err([string]$m) { Write-Host "[ERR] $m" -ForegroundColor Red }

function Test-Admin {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $p = New-Object Security.Principal.WindowsPrincipal($id)
        return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch { return $false }
}

function Ensure-Command([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Ensure-Python {
    if (Ensure-Command "python") { return }
    if (!(Ensure-Command "winget")) { throw "Python não encontrado e winget não disponível." }
    Write-Inf "Instalando Python via winget..."
    & winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements | Out-Null
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    if (!(Ensure-Command "python")) { throw "Falha ao instalar Python via winget." }
}

function Ensure-MediaMTX {
    $mtxPath = Join-Path $installDir "bin\mediamtx.exe"
    if (Test-Path $mtxPath) { return }

    Write-Inf "Baixando MediaMTX (Media Server para WebRTC/HLS)..."
    $url = "https://github.com/bluenviron/mediamtx/releases/download/v1.9.0/mediamtx_v1.9.0_windows_amd64.zip"
    $tmp = Join-Path $env:TEMP "mediamtx-install"
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $zip = Join-Path $tmp "mediamtx.zip"
    
    try {
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $bin = Join-Path $tmp "mediamtx.exe"
        $yml = Join-Path $tmp "mediamtx.yml"
        $destBin = Join-Path $installDir "bin"
        New-Item -ItemType Directory -Force -Path $destBin | Out-Null
        if (Test-Path $bin) { Copy-Item $bin $destBin -Force }
        if (Test-Path $yml) { Copy-Item $yml $destBin -Force }
        Write-Ok "MediaMTX instalado em $destBin"
    } catch {
        Write-Wrn "Não foi possível baixar MediaMTX. O vídeo WebRTC pode falhar."
    } finally {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-Ffmpeg {
    $destBin = Join-Path $installDir "bin"
    $destFfmpeg = Join-Path $destBin "ffmpeg.exe"

    if (Ensure-Command "ffmpeg") {
        try {
            New-Item -ItemType Directory -Force -Path $destBin | Out-Null
            $src = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
            if ($src -and (Test-Path $src)) {
                Copy-Item $src $destFfmpeg -Force
                Write-Ok "ffmpeg disponível (copiado para $destFfmpeg)"
                return
            }
        } catch {}
        return
    }
    
    # Tenta via winget primeiro (método oficial e mais limpo)
    if (Ensure-Command "winget") {
        Write-Inf "Instalando ffmpeg via winget..."
        try {
            & winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements --silent | Out-Null
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
            if (Ensure-Command "ffmpeg") {
                try {
                    New-Item -ItemType Directory -Force -Path $destBin | Out-Null
                    $src = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
                    if ($src -and (Test-Path $src)) { Copy-Item $src $destFfmpeg -Force }
                } catch {}
                Write-Ok "ffmpeg instalado com sucesso."
                return
            }
        } catch {}
    }

    # Backup: Download direto se winget falhar ou não existir
    Write-Inf "Baixando ffmpeg portátil..."
    $ffmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    $ffmpegTmp = Join-Path $env:TEMP "ffmpeg-install"
    $ffmpegZip = Join-Path $ffmpegTmp "ffmpeg.zip"
    New-Item -ItemType Directory -Force -Path $ffmpegTmp | Out-Null
    
    try {
        Invoke-WebRequest -Uri $ffmpegUrl -OutFile $ffmpegZip -UseBasicParsing
        Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegTmp -Force
        $binFolder = Get-ChildItem -Path $ffmpegTmp -Directory -Recurse | Where-Object { $_.Name -eq "bin" } | Select-Object -First 1
        if ($binFolder) {
            New-Item -ItemType Directory -Force -Path $destBin | Out-Null
            Copy-Item (Join-Path $binFolder.FullName "*") $destBin -Force
            # Adiciona ao PATH da sessão atual
            $env:Path += ";$destBin"
            Write-Ok "ffmpeg portátil instalado em $destBin"
        }
    } catch {
        Write-Wrn "Não foi possível instalar ffmpeg automaticamente. As câmeras podem não funcionar."
    } finally {
        Remove-Item $ffmpegTmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Read-EnvValue([string]$envPath, [string]$key) {
    try {
        if (!(Test-Path $envPath)) { return "" }
        $lines = Get-Content $envPath -ErrorAction SilentlyContinue
        foreach ($ln in $lines) {
            if ($ln -match ("^" + [Regex]::Escape($key) + "=(.*)$")) {
                return $Matches[1]
            }
        }
    } catch {}
    return ""
}

function Stop-EdgeRuntime([string]$rootDir) {
    $taskName = "ETI_SENTINEL_EDGE"
    try { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue } catch {}
    try { Disable-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null } catch {}
    try {
        Get-ScheduledTask -TaskName "ETI_SENTINEL_*" -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-ScheduledTask -TaskName $_.TaskName -ErrorAction SilentlyContinue }
    } catch {}

    $root = $rootDir
    if ($root) { $root = $root.TrimEnd("\") + "\" }
    try {
        Get-CimInstance Win32_Process |
            Where-Object {
                ($_.ExecutablePath -and $root -and $_.ExecutablePath -like ($root + "*")) -or
                ($_.CommandLine -and $root -and $_.CommandLine -like ("*" + $root + "*"))
            } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch {}
    try {
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.ExecutablePath -and $_.ExecutablePath -like "*\\ETI-SENTINEL*\\bin\\mediamtx.exe"
            } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch {}
    try {
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.ExecutablePath -and (
                    $_.ExecutablePath -like "*\\ETI-SENTINEL*\\bin\\ffmpeg.exe" -or
                    $_.ExecutablePath -like "*\\ETI-SENTINEL*\\bin\\ffprobe.exe"
                )
            } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    } catch {}

    try { Start-Sleep -Seconds 2 } catch {}
}

function Download-Repo([string]$destDir) {
    Stop-EdgeRuntime $destDir

    $backupEnv = ""
    try {
        $oldEnv = Join-Path $destDir "edge-agent\.env"
        if (Test-Path $oldEnv) {
            $backupEnv = Join-Path $env:TEMP ("eti-edge-env-" + [Guid]::NewGuid().ToString("N") + ".env")
            Copy-Item $oldEnv $backupEnv -Force
        }
    } catch {}

    $tmp = Join-Path $env:TEMP ("eti-sentinel-main-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $zip = Join-Path $tmp "main.zip"
    $url = "https://github.com/etitecnologies-sketch/ETI-SENTINEL/archive/refs/heads/main.zip"
    Write-Inf "Baixando ETI-SENTINEL (main.zip)..."
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Write-Inf "Extraindo..."
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $src = Get-ChildItem -Path $tmp -Directory | Where-Object { $_.Name -like "ETI-SENTINEL-*" } | Select-Object -First 1
    if (!$src) { throw "Não foi possível localizar pasta extraída do repositório." }
    if (Test-Path $destDir) {
        try {
            Remove-Item $destDir -Recurse -Force -ErrorAction Stop
        } catch {
            try {
                Start-Sleep -Seconds 2
                Stop-EdgeRuntime $destDir
                Remove-Item $destDir -Recurse -Force -ErrorAction Stop
            } catch {
                $old = ($destDir.TrimEnd("\") + ".old." + (Get-Date -Format "yyyyMMdd_HHmmss"))
                Write-Wrn "Pasta em uso. Renomeando para: $old"
                try { Rename-Item -Path $destDir -NewName $old -Force } catch {}
            }
        }
    }
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    try {
        Copy-Item (Join-Path $src.FullName "*") $destDir -Recurse -Force -ErrorAction Stop
    } catch {
        Stop-EdgeRuntime $destDir
        try {
            Copy-Item (Join-Path $src.FullName "*") $destDir -Recurse -Force -ErrorAction Stop
        } catch {
            Write-Wrn "Falha ao copiar binários em uso. Continuando sem sobrescrever executáveis."
            Copy-Item (Join-Path $src.FullName "*") $destDir -Recurse -Force -Exclude "mediamtx.exe","ffmpeg.exe","ffprobe.exe"
        }
    }
    Remove-Item $tmp -Recurse -Force

    try {
        if ($backupEnv) {
            $edgeDir = Join-Path $destDir "edge-agent"
            New-Item -ItemType Directory -Force -Path $edgeDir | Out-Null
            Copy-Item $backupEnv (Join-Path $edgeDir ".env") -Force
            Remove-Item $backupEnv -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

function Ensure-Env([string]$edgeDir, [string]$ingest, [string]$key, [string]$cid) {
    $envPath = Join-Path $edgeDir ".env"
    if (!(Test-Path $envPath)) {
        $ex = Join-Path $edgeDir ".env.example"
        if (Test-Path $ex) { Copy-Item $ex $envPath -Force } else { New-Item -ItemType File -Force -Path $envPath | Out-Null }
    }
    $lines = @()
    if (Test-Path $envPath) { $lines = Get-Content $envPath -ErrorAction SilentlyContinue }
    $lines = $lines | Where-Object { $_ -notmatch '^(INGEST_API_URL|COLLECTOR_KEY|CLIENT_ID|ENABLE_STREAMING|ENABLE_RTSP_MONITOR|AGENT_API_BIND|AGENT_API_PORT|EDGE_USE_PYTHONW|EDGE_EVENT_DEDUPE_SECONDS|EDGE_VIDEOLOSS_CONFIRM_SECONDS|EDGE_RECOVERY_CONFIRM_SECONDS|EDGE_VIDEOLOSS_MIN_SECONDS|EDGE_NOTIFY_RECOVERY|EDGE_SUPPRESS_EVENT_TYPES|STREAM_RESTART_COOLDOWN_SECONDS|STREAM_MAX_RETRIES|STREAM_RETRY_MAX_BACKOFF_SECONDS)=' }
    $lines += "INGEST_API_URL=$ingest"
    $lines += "COLLECTOR_KEY=$key"
    if ($cid) { $lines += "CLIENT_ID=$cid" }
    $lines += "ENABLE_STREAMING=1"
    $lines += "ENABLE_RTSP_MONITOR=0"
    $lines += "AGENT_API_BIND=127.0.0.1"
    $lines += "AGENT_API_PORT=8808"
    $lines += "EDGE_USE_PYTHONW=1"
    $lines += "EDGE_EVENT_DEDUPE_SECONDS=600"
    $lines += "EDGE_VIDEOLOSS_CONFIRM_SECONDS=15"
    $lines += "EDGE_RECOVERY_CONFIRM_SECONDS=10"
    $lines += "EDGE_VIDEOLOSS_MIN_SECONDS=30"
    $lines += "EDGE_NOTIFY_RECOVERY=0"
    $lines += "EDGE_SUPPRESS_EVENT_TYPES="
    $lines += "STREAM_RESTART_COOLDOWN_SECONDS=60"
    $lines += "STREAM_MAX_RETRIES=0"
    $lines += "STREAM_RETRY_MAX_BACKOFF_SECONDS=60"
    [System.IO.File]::WriteAllLines($envPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
}

function Ensure-Venv([string]$edgeDir) {
    $venv = Join-Path $edgeDir ".venv"
    $py = Join-Path $venv "Scripts\python.exe"
    if (!(Test-Path $py)) {
        Write-Inf "Criando ambiente virtual..."
        & python -m venv $venv | Out-Null
    }
    try {
        $installDir = Split-Path -Parent $edgeDir
        $cacheDir = Join-Path $installDir ".pip-cache"
        New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
        $env:PIP_CACHE_DIR = $cacheDir
    } catch {}
    Write-Inf "Instalando dependências do Edge..."
    & $py -m pip install --upgrade pip --no-cache-dir | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar/atualizar pip na venv." }
    & $py -m pip install --no-cache-dir -r (Join-Path $edgeDir "requirements.txt") | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar requirements do Edge." }
}

function Ensure-Icon([string]$installDir) {
    $edgeDir = Join-Path $installDir "edge-agent"
    $py = Join-Path $edgeDir ".venv\Scripts\python.exe"
    $src = Join-Path $installDir "imag\ETI SENTINEL-logo.jpg"
    $dst = Join-Path $edgeDir "ETI_SENTINEL.ico"
    if (!(Test-Path $py)) { return }
    if (!(Test-Path $src)) { return }
    Write-Inf "Gerando ícone do ETI SENTINEL..."
    $code = @"
from PIL import Image
src = r'''$src'''
dst = r'''$dst'''
img = Image.open(src)
img = img.convert('RGBA')
sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
img.save(dst, format='ICO', sizes=sizes)
"@
    & $py -c $code | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar .ico (Pillow/arquivo fonte)." }
    if (!(Test-Path $dst)) { throw "Falha ao gerar ícone: $dst" }
}

function Ensure-Shortcuts([string]$installDir) {
    $edgeDir = Join-Path $installDir "edge-agent"
    $pythonw = Join-Path $edgeDir ".venv\Scripts\pythonw.exe"
    $icon = Join-Path $edgeDir "ETI_SENTINEL.ico"
    $tray = Join-Path $edgeDir "tray_app.py"
    $localUrl = "http://127.0.0.1:8808"
    $desktop = [Environment]::GetFolderPath("Desktop")
    $programs = [Environment]::GetFolderPath("Programs")
    $folder = Join-Path $programs "ETI SENTINEL"
    New-Item -ItemType Directory -Force -Path $folder | Out-Null

    if (!(Test-Path $icon)) { Ensure-Icon $installDir }
    $shell = New-Object -ComObject WScript.Shell
    $lnk1 = $shell.CreateShortcut((Join-Path $desktop "ETI SENTINEL.lnk"))
    $lnk1 = $shell.CreateShortcut((Join-Path $desktop "ETI SENTINEL.lnk"))
    $lnk1.TargetPath = "explorer.exe"
    $lnk1.Arguments = $localUrl
    $lnk1.WorkingDirectory = $installDir
    $lnk1.Description = "ETI SENTINEL - Abrir Painel Local"
    if (Test-Path $icon) { $lnk1.IconLocation = "$icon,0" }
    $lnk1.Save()
    $lnk2 = $shell.CreateShortcut((Join-Path $folder "ETI SENTINEL.lnk"))
    $lnk2 = $shell.CreateShortcut((Join-Path $folder "ETI SENTINEL.lnk"))
    $lnk2.TargetPath = "explorer.exe"
    $lnk2.Arguments = $localUrl
    $lnk2.WorkingDirectory = $installDir
    $lnk2.Description = "ETI SENTINEL - Abrir Painel Local"
    if (Test-Path $icon) { $lnk2.IconLocation = "$icon,0" }
    $lnk2.Save()

    if ((Test-Path $pythonw) -and (Test-Path $tray)) {
        $lnk3 = $shell.CreateShortcut((Join-Path $folder "ETI SENTINEL (Tray).lnk"))
        $lnk3.TargetPath = $pythonw
        $lnk3.Arguments = "`"$tray`""
        $lnk3.WorkingDirectory = $edgeDir
        $lnk3.Description = "ETI SENTINEL - Ícone na bandeja"
        if (Test-Path $icon) { $lnk3.IconLocation = "$icon,0" }
        $lnk3.Save()
    }
    $un = $shell.CreateShortcut((Join-Path $folder "Desinstalar ETI SENTINEL.lnk"))
    $un.TargetPath = "powershell.exe"
    $un.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$installDir\edge-installer\Uninstall-ETI-SENTINEL-Edge.ps1`""
    $un.WorkingDirectory = $installDir
    $un.Description = "Desinstalar ETI SENTINEL - Edge Agent"
    if (Test-Path $icon) { $un.IconLocation = "$icon,0" }
    $un.Save()
}


function Ensure-Task([string]$installDir) {
    $edgeDir = Join-Path $installDir "edge-agent"
    $pythonw = Join-Path $edgeDir ".venv\Scripts\pythonw.exe"
    $entry = Join-Path $edgeDir "edge_agent.py"
    $taskName = "ETI_SENTINEL_EDGE"

    try {
        Get-ScheduledTask -TaskName "ETI_SENTINEL_*" -ErrorAction SilentlyContinue |
            Where-Object { $_.TaskName -ne $taskName } |
            ForEach-Object { Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null }
    } catch {}

    try { Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue } catch {}
    try { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null } catch {}

    $action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$entry`"" -WorkingDirectory $edgeDir
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    if (Test-Admin) {
        $trigger = New-ScheduledTaskTrigger -AtStartup
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -User "SYSTEM" -Force | Out-Null
    } else {
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null
    }
    Start-ScheduledTask -TaskName $taskName
}

$installDir = Join-Path $env:LOCALAPPDATA "ETI-SENTINEL"
Write-Inf "Instalação em: $installDir"

Ensure-Python
Ensure-Ffmpeg
Ensure-MediaMTX

$existingEnv = Join-Path $installDir "edge-agent\.env"
$defaultIngest = (Read-EnvValue $existingEnv "INGEST_API_URL").Trim()
if (!$defaultIngest) { $defaultIngest = "https://eti-sentinel-production.up.railway.app" }
$defaultKey = (Read-EnvValue $existingEnv "COLLECTOR_KEY").Trim()
if (!$defaultKey) { $defaultKey = "etiSENTINEL_collector_2026_etitecnologies" }
$defaultCid = (Read-EnvValue $existingEnv "CLIENT_ID").Trim()

$ingest = $Ingest.Trim()
if (!$ingest -and $Update) { $ingest = $defaultIngest }
if (!$ingest) { $ingest = (Read-Host "INGEST_API_URL (Enter = $defaultIngest)").Trim() }
if (!$ingest) { $ingest = $defaultIngest }
$ingest = $ingest.Trim('`').Trim('"').Trim("'").Trim()
if (!($ingest.StartsWith("http://") -or $ingest.StartsWith("https://"))) { $ingest = "https://$ingest" }
$ingest = $ingest.TrimEnd("/")

$key = $CollectorKey.Trim()
if (!$key -and $Update) { $key = $defaultKey }
if (!$key) { $key = (Read-Host "COLLECTOR_KEY (Enter = default)").Trim() }
if (!$key) { $key = $defaultKey }
$key = $key.Trim('`').Trim('"').Trim("'").Trim()
if (!$key) { throw "COLLECTOR_KEY é obrigatório." }

$cid = $ClientId.Trim()
if (!$cid -and $Update) { $cid = $defaultCid }
if (!$cid) { $cid = (Read-Host "CLIENT_ID (opcional)").Trim() }
$cid = $cid.Trim('`').Trim('"').Trim("'").Trim()

Download-Repo $installDir
$edgeDir = Join-Path $installDir "edge-agent"
Ensure-Env $edgeDir $ingest $key $cid
Ensure-Ffmpeg
Ensure-MediaMTX
Ensure-Venv $edgeDir
Ensure-Task $installDir
Ensure-Icon $installDir
Ensure-Shortcuts $installDir

Write-Ok "Instalado. Edge iniciado e configurado para iniciar com o Windows."
Write-Inf "Status: http://127.0.0.1:8808/api/status"
