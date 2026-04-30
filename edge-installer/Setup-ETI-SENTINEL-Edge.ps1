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

function Ensure-Ffmpeg {
    if (Ensure-Command "ffmpeg") { return }
    if (!(Ensure-Command "winget")) { Write-Wrn "ffmpeg não encontrado e winget não disponível."; return }
    Write-Inf "Instalando ffmpeg via winget..."
    & winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements | Out-Null
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

function Download-Repo([string]$destDir) {
    try { Stop-ScheduledTask -TaskName "ETI_SENTINEL_EDGE" -ErrorAction SilentlyContinue } catch {}
    try {
        Get-ScheduledTask -TaskName "ETI_SENTINEL_*" -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-ScheduledTask -TaskName $_.TaskName -ErrorAction SilentlyContinue }
    } catch {}
    try {
        Get-CimInstance Win32_Process |
            Where-Object { $_.CommandLine -and ($_.CommandLine -like "*\\ETI-SENTINEL\\*") } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
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
                Remove-Item $destDir -Recurse -Force -ErrorAction Stop
            } catch {
                $old = ($destDir.TrimEnd("\") + ".old." + (Get-Date -Format "yyyyMMdd_HHmmss"))
                Write-Wrn "Pasta em uso. Renomeando para: $old"
                try { Rename-Item -Path $destDir -NewName $old -Force } catch {}
            }
        }
    }
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Copy-Item (Join-Path $src.FullName "*") $destDir -Recurse -Force
    Remove-Item $tmp -Recurse -Force
}

function Ensure-Env([string]$edgeDir, [string]$ingest, [string]$key, [string]$cid) {
    $envPath = Join-Path $edgeDir ".env"
    if (!(Test-Path $envPath)) {
        $ex = Join-Path $edgeDir ".env.example"
        if (Test-Path $ex) { Copy-Item $ex $envPath -Force } else { New-Item -ItemType File -Force -Path $envPath | Out-Null }
    }
    $lines = @()
    if (Test-Path $envPath) { $lines = Get-Content $envPath -ErrorAction SilentlyContinue }
    $lines = $lines | Where-Object { $_ -notmatch '^(INGEST_API_URL|COLLECTOR_KEY|CLIENT_ID)=' }
    $lines += "INGEST_API_URL=$ingest"
    $lines += "COLLECTOR_KEY=$key"
    if ($cid) { $lines += "CLIENT_ID=$cid" }
    [System.IO.File]::WriteAllLines($envPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
}

function Ensure-Venv([string]$edgeDir) {
    $venv = Join-Path $edgeDir ".venv"
    $py = Join-Path $venv "Scripts\python.exe"
    if (!(Test-Path $py)) {
        Write-Inf "Criando ambiente virtual..."
        & python -m venv $venv | Out-Null
    }
    Write-Inf "Instalando dependências do Edge..."
    & $py -m pip install --upgrade pip | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar/atualizar pip na venv." }
    & $py -m pip install -r (Join-Path $edgeDir "requirements.txt") | Out-Null
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
img = img.convert("RGBA")
sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
img.save(dst, format="ICO", sizes=sizes)
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
    if (Test-Admin) {
        $trigger = New-ScheduledTaskTrigger -AtStartup
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -RunLevel Highest -User "SYSTEM" -Force | Out-Null
    } else {
        $trigger = New-ScheduledTaskTrigger -AtLogOn
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -RunLevel Highest -Force | Out-Null
    }
    Start-ScheduledTask -TaskName $taskName
}

$installDir = Join-Path $env:LOCALAPPDATA "ETI-SENTINEL"
Write-Inf "Instalação em: $installDir"

Ensure-Python
Ensure-Ffmpeg

$defaultIngest = "https://eti-sentinel-production.up.railway.app"
$defaultKey = "etiSENTINEL_collector_2026_etitecnologies"

$ingest = (Read-Host "INGEST_API_URL (Enter = $defaultIngest)").Trim()
if (!$ingest) { $ingest = $defaultIngest }
$ingest = $ingest.Trim('`').Trim('"').Trim("'").Trim()
if (!($ingest.StartsWith("http://") -or $ingest.StartsWith("https://"))) { $ingest = "https://$ingest" }
$ingest = $ingest.TrimEnd("/")

$key = (Read-Host "COLLECTOR_KEY (Enter = default)").Trim()
if (!$key) { $key = $defaultKey }
$key = $key.Trim('`').Trim('"').Trim("'").Trim()
if (!$key) { throw "COLLECTOR_KEY é obrigatório." }

$cid = (Read-Host "CLIENT_ID (opcional)").Trim()
$cid = $cid.Trim('`').Trim('"').Trim("'").Trim()

Download-Repo $installDir
$edgeDir = Join-Path $installDir "edge-agent"
Ensure-Env $edgeDir $ingest $key $cid
Ensure-Venv $edgeDir
Ensure-Task $installDir
Ensure-Icon $installDir
Ensure-Shortcuts $installDir

Write-Ok "Instalado. Edge iniciado e configurado para iniciar com o Windows."
Write-Inf "Status: http://127.0.0.1:8808/api/status"
