param(
    [string]$Ingest,
    [string]$CollectorKey,
    [string]$ClientId,
    [switch]$Update,
    [string]$OfflineBundle
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

if (!(Test-Admin)) {
    Write-Wrn "Este instalador precisa ser executado como Administrador para garantir boot sem logon e recuperação automática."
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    if ($Ingest) { $argList += @("-Ingest", $Ingest) }
    if ($CollectorKey) { $argList += @("-CollectorKey", $CollectorKey) }
    if ($ClientId) { $argList += @("-ClientId", $ClientId) }
    if ($Update) { $argList += "-Update" }
    try {
        Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argList | Out-Null
        exit 0
    } catch {
        throw "Falha ao elevar privilégios. Reexecute como Administrador."
    }
}

$script:OfflineRoot = ""
$script:OfflineTemp = ""

function Resolve-OfflineRoot {
    $p = ("" + ($OfflineBundle)).Trim()
    if (!$p) {
        $p = ("" + ($env:ETI_OFFLINE_BUNDLE)).Trim()
    }
    if (!$p) { return "" }
    $p = $p.Trim('`"').Trim("'")
    if (!(Test-Path $p)) { throw "OfflineBundle não encontrado: $p" }
    if ($p.ToLower().EndsWith(".zip")) {
        $tmp = Join-Path $env:TEMP ("eti-offline-" + [Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        Expand-Archive -Path $p -DestinationPath $tmp -Force
        $script:OfflineTemp = $tmp
        $script:OfflineRoot = $tmp
        return $tmp
    }
    $script:OfflineRoot = $p
    return $p
}

function Offline-File([string]$rel) {
    $root = $script:OfflineRoot
    if (!$root) { return "" }
    $fp = Join-Path $root $rel
    if (Test-Path $fp) { return $fp }
    return ""
}

Resolve-OfflineRoot | Out-Null

function Ensure-Command([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Test-ZipFile([string]$path) {
    try {
        if (!(Test-Path $path)) { return $false }
        $fs = [System.IO.File]::OpenRead($path)
        try {
            $zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Read, $false)
            try {
                return ($zip.Entries.Count -ge 0)
            } finally {
                $zip.Dispose()
            }
        } finally {
            $fs.Dispose()
        }
    } catch {
        return $false
    }
}

function Download-File([string]$url, [string]$dest, [switch]$IsZip) {
    $destDir = Split-Path -Parent $dest
    if ($destDir) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
    for ($i = 1; $i -le 3; $i++) {
        try {
            if (Test-Path $dest) { Remove-Item $dest -Force -ErrorAction SilentlyContinue }
            $ok = $false
            if (Ensure-Command "Start-BitsTransfer") {
                try {
                    Start-BitsTransfer -Source $url -Destination $dest -ErrorAction Stop
                    $ok = $true
                } catch {
                    $ok = $false
                }
            }
            if (-not $ok) {
                Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"} -ErrorAction Stop
            }
            if (!(Test-Path $dest)) { throw "download_missing" }
            $len = (Get-Item $dest).Length
            if ($len -lt 1024) { throw "download_too_small:$len" }
            if ($IsZip) {
                if (!(Test-ZipFile $dest)) { throw "zip_invalid" }
            }
            return
        } catch {
            if ($i -eq 3) { throw }
            Start-Sleep -Seconds (2 * $i)
        }
    }
}

function Ensure-WinSW {
    $destBin = Join-Path $installDir "bin"
    $winsw = Join-Path $destBin "winsw.exe"
    if (Test-Path $winsw) { return $winsw }
    New-Item -ItemType Directory -Force -Path $destBin | Out-Null
    $offline = (Offline-File "winsw\\winsw.exe")
    if (!$offline) { $offline = (Offline-File "winsw\\WinSW-x64.exe") }
    if ($offline) {
        Copy-Item $offline $winsw -Force
        return $winsw
    }
    Write-Inf "Baixando WinSW (Windows Service Wrapper)..."
    $url = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
    try {
        Download-File $url $winsw
        return $winsw
    } catch {
        throw "Não foi possível baixar WinSW automaticamente. Verifique internet/proxy e tente novamente."
    }
}

function Write-ServiceConfig([string]$xmlPath, [string]$id, [string]$name, [string]$description, [string]$exe, [string]$args, [string]$workDir, [hashtable]$envMap, [string[]]$depends) {
    $logDir = Join-Path $installDir ".logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $envLines = ""
    if ($envMap) {
        foreach ($k in $envMap.Keys) {
            $kk = [Security.SecurityElement]::Escape([string]$k)
            $vv = [Security.SecurityElement]::Escape([string]$envMap[$k])
            $envLines += "  <env name=`"$kk`" value=`"$vv`" />`r`n"
        }
    }
    $depLines = ""
    if ($depends) {
        foreach ($d in $depends) {
            $dd = [Security.SecurityElement]::Escape([string]$d)
            if ($dd) { $depLines += "  <depend>$dd</depend>`r`n" }
        }
    }
    $exeEsc = [Security.SecurityElement]::Escape($exe)
    $argsEsc = [Security.SecurityElement]::Escape($args)
    $workEsc = [Security.SecurityElement]::Escape($workDir)
    $idEsc = [Security.SecurityElement]::Escape($id)
    $nameEsc = [Security.SecurityElement]::Escape($name)
    $descEsc = [Security.SecurityElement]::Escape($description)
    $logEsc = [Security.SecurityElement]::Escape($logDir)

    $xml = @"
<service>
  <id>$idEsc</id>
  <name>$nameEsc</name>
  <description>$descEsc</description>
  <startmode>Automatic</startmode>
  <delayedAutoStart>true</delayedAutoStart>
  <logpath>$logEsc</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10485760</sizeThreshold>
    <keepFiles>8</keepFiles>
  </log>
$envLines$depLines  <executable>$exeEsc</executable>
  <arguments>$argsEsc</arguments>
  <workingdirectory>$workEsc</workingdirectory>
  <onfailure action="restart" delay="10 sec" />
  <onfailure action="restart" delay="30 sec" />
  <onfailure action="restart" delay="2 min" />
</service>
"@
    [System.IO.File]::WriteAllText($xmlPath, $xml, (New-Object System.Text.UTF8Encoding($false)))
}

function Ensure-Services([string]$installDir) {
    $edgeDir = Join-Path $installDir "edge-agent"
    $venvPy = Join-Path $edgeDir ".venv\Scripts\python.exe"
    $edgeEntry = Join-Path $edgeDir "edge_agent.py"
    $binDir = Join-Path $installDir "bin"
    $mtxExe = Join-Path $binDir "mediamtx.exe"

    $winsw = Ensure-WinSW
    $svcEdgeExe = Join-Path $binDir "ETI_SENTINEL_EDGE_AGENT.exe"
    $svcEdgeXml = Join-Path $binDir "ETI_SENTINEL_EDGE_AGENT.xml"
    $svcMtxExe = Join-Path $binDir "ETI_SENTINEL_MEDIAMTX.exe"
    $svcMtxXml = Join-Path $binDir "ETI_SENTINEL_MEDIAMTX.xml"

    Copy-Item $winsw $svcEdgeExe -Force
    Copy-Item $winsw $svcMtxExe -Force

    $edgeArgs = ('-u "{0}"' -f $edgeEntry)
    Write-ServiceConfig $svcEdgeXml "ETI_SENTINEL_EDGE_AGENT" "ETI SENTINEL Edge Agent" "ETI SENTINEL Edge Agent (24/7)" $venvPy $edgeArgs $edgeDir @{
        "PYTHONUTF8" = "1"
        "PYTHONUNBUFFERED" = "1"
    } @("ETI_SENTINEL_MEDIAMTX")
    Write-ServiceConfig $svcMtxXml "ETI_SENTINEL_MEDIAMTX" "ETI SENTINEL MediaMTX" "ETI SENTINEL MediaMTX (WebRTC/HLS)" $mtxExe "" $binDir @{} @()

    try {
        & $svcEdgeExe stop | Out-Null
    } catch {}
    try {
        & $svcMtxExe stop | Out-Null
    } catch {}
    try {
        & $svcEdgeExe uninstall | Out-Null
    } catch {}
    try {
        & $svcMtxExe uninstall | Out-Null
    } catch {}

    Write-Inf "Instalando serviços Windows (boot sem logon + auto-restart)..."

    try {
        Get-ScheduledTask -TaskName "ETI_SENTINEL_*" -ErrorAction SilentlyContinue |
            ForEach-Object { Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null }
    } catch {}

    & $svcMtxExe install | Out-Null
    & $svcEdgeExe install | Out-Null
    & $svcMtxExe start | Out-Null
    & $svcEdgeExe start | Out-Null
}

function Ensure-Python {
    if (Ensure-Command "python") {
        $script:PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
        return
    }

    $offlinePy = (Offline-File "python\\python-installer.exe")
    if (!$offlinePy) {
        $candidates = @(
            (Offline-File "python\\python-3.12.10-amd64.exe"),
            (Offline-File "python\\python-3.12.9-amd64.exe"),
            (Offline-File "python\\python-3.12.8-amd64.exe")
        ) | Where-Object { $_ }
        if ($candidates -and $candidates.Count -gt 0) { $offlinePy = $candidates[0] }
    }
    if ($offlinePy) {
        Write-Inf "Instalando Python via pacote offline..."
        $pyDir = Join-Path $installDir "python"
        New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
        $args = @(
            "/quiet",
            "InstallAllUsers=1",
            "Include_pip=1",
            "Include_test=0",
            "PrependPath=0",
            "TargetDir=$pyDir"
        )
        $p = Start-Process -FilePath $offlinePy -ArgumentList $args -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "python_install_failed:$($p.ExitCode)" }
        $pyExe = Join-Path $pyDir "python.exe"
        if (!(Test-Path $pyExe)) { throw "python_not_found_after_offline_install" }
        $script:PythonExe = $pyExe
        $env:Path = "$pyDir;" + $env:Path
        return
    }

    if (Ensure-Command "winget") {
        Write-Inf "Instalando Python via winget..."
        & winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements | Out-Null
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        if (!(Ensure-Command "python")) { throw "Falha ao instalar Python via winget." }
        $script:PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
        return
    }

    Write-Inf "Python não encontrado. Baixando instalador oficial..."
    $pyDir = Join-Path $installDir "python"
    $tmp = Join-Path $env:TEMP ("python-installer-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $exe = Join-Path $tmp "python.exe"
    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
    try {
        Download-File $url $exe
        New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
        $args = @(
            "/quiet",
            "InstallAllUsers=1",
            "Include_pip=1",
            "Include_test=0",
            "PrependPath=0",
            "TargetDir=$pyDir"
        )
        $p = Start-Process -FilePath $exe -ArgumentList $args -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "python_install_failed:$($p.ExitCode)" }
        $pyExe = Join-Path $pyDir "python.exe"
        if (!(Test-Path $pyExe)) { throw "python_not_found_after_install" }
        $script:PythonExe = $pyExe
        $env:Path = "$pyDir;" + $env:Path
    } finally {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-MediaMTX {
    $mtxPath = Join-Path $installDir "bin\mediamtx.exe"
    if (Test-Path $mtxPath) {
        Ensure-MediaMTXConfig
        return
    }

    $destBin = Join-Path $installDir "bin"
    New-Item -ItemType Directory -Force -Path $destBin | Out-Null
    $offlineExe = (Offline-File "mediamtx\\mediamtx.exe")
    $offlineZip = (Offline-File "mediamtx\\mediamtx.zip")
    if (!$offlineZip) { $offlineZip = (Offline-File "mediamtx\\mediamtx_v1.9.0_windows_amd64.zip") }
    if ($offlineExe) {
        Copy-Item $offlineExe $destBin -Force
        $offlineYml = (Offline-File "mediamtx\\mediamtx.yml")
        if ($offlineYml) { Copy-Item $offlineYml $destBin -Force }
        Ensure-MediaMTXConfig
        Write-Ok "MediaMTX instalado (offline) em $destBin"
        return
    }
    if ($offlineZip) {
        Write-Inf "Instalando MediaMTX via pacote offline..."
        $tmp = Join-Path $env:TEMP "mediamtx-install"
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        try {
            Expand-Archive -Path $offlineZip -DestinationPath $tmp -Force
            $bin = Join-Path $tmp "mediamtx.exe"
            $yml = Join-Path $tmp "mediamtx.yml"
            if (Test-Path $bin) { Copy-Item $bin $destBin -Force }
            if (Test-Path $yml) { Copy-Item $yml $destBin -Force }
            Ensure-MediaMTXConfig
            Write-Ok "MediaMTX instalado (offline) em $destBin"
            return
        } catch {
            Write-Wrn "Pacote offline do MediaMTX inválido. Tentando download online."
        } finally {
            Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Inf "Baixando MediaMTX (Media Server para WebRTC/HLS)..."
    $url = "https://github.com/bluenviron/mediamtx/releases/download/v1.9.0/mediamtx_v1.9.0_windows_amd64.zip"
    $tmp = Join-Path $env:TEMP "mediamtx-install"
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    $zip = Join-Path $tmp "mediamtx.zip"
    
    try {
        Download-File $url $zip -IsZip
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $bin = Join-Path $tmp "mediamtx.exe"
        $yml = Join-Path $tmp "mediamtx.yml"
        $destBin = Join-Path $installDir "bin"
        New-Item -ItemType Directory -Force -Path $destBin | Out-Null
        if (Test-Path $bin) { Copy-Item $bin $destBin -Force }
        if (Test-Path $yml) { Copy-Item $yml $destBin -Force }
        Ensure-MediaMTXConfig
        Write-Ok "MediaMTX instalado em $destBin"
    } catch {
        Write-Wrn "Não foi possível baixar MediaMTX. O vídeo WebRTC pode falhar."
    } finally {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-MediaMTXConfig {
    $ymlPath = Join-Path $installDir "bin\mediamtx.yml"
    if (!(Test-Path $ymlPath)) { return }
    try {
        $lines = Get-Content $ymlPath -ErrorAction SilentlyContinue
        if (!$lines) { $lines = @() }
        $out = @()
        $patched = $false
        foreach ($ln in $lines) {
            if ($ln -match '^\s*rtspTransports\s*:') { continue }
            if ($ln -match '^\s*protocols\s*:') {
                $out += "protocols: [tcp]"
                $patched = $true
                continue
            }
            $out += $ln
        }
        if (-not $patched) {
            $out += "protocols: [tcp]"
        }
        $txt = ($out -join "`r`n") + "`r`n"
        [System.IO.File]::WriteAllText($ymlPath, $txt, (New-Object System.Text.UTF8Encoding($false)))
    } catch {}
}

function Ensure-Ffmpeg {
    $destBin = Join-Path $installDir "bin"
    $destFfmpeg = Join-Path $destBin "ffmpeg.exe"

    $offlineFfmpeg = (Offline-File "ffmpeg\\ffmpeg.exe")
    $offlineFfprobe = (Offline-File "ffmpeg\\ffprobe.exe")
    $offlineZip = (Offline-File "ffmpeg\\ffmpeg.zip")
    if (!$offlineZip) { $offlineZip = (Offline-File "ffmpeg\\ffmpeg-release-essentials.zip") }
    if ($offlineFfmpeg) {
        New-Item -ItemType Directory -Force -Path $destBin | Out-Null
        Copy-Item $offlineFfmpeg $destFfmpeg -Force
        if ($offlineFfprobe) { Copy-Item $offlineFfprobe (Join-Path $destBin "ffprobe.exe") -Force }
        $env:Path += ";$destBin"
        Write-Ok "ffmpeg instalado (offline) em $destBin"
        return
    }
    if ($offlineZip) {
        Write-Inf "Instalando ffmpeg via pacote offline..."
        $ffmpegTmp = Join-Path $env:TEMP "ffmpeg-install"
        New-Item -ItemType Directory -Force -Path $ffmpegTmp | Out-Null
        try {
            Expand-Archive -Path $offlineZip -DestinationPath $ffmpegTmp -Force
            $binFolder = Get-ChildItem -Path $ffmpegTmp -Directory -Recurse | Where-Object { $_.Name -eq "bin" } | Select-Object -First 1
            if ($binFolder) {
                New-Item -ItemType Directory -Force -Path $destBin | Out-Null
                Copy-Item (Join-Path $binFolder.FullName "*") $destBin -Force
                $env:Path += ";$destBin"
                Write-Ok "ffmpeg instalado (offline) em $destBin"
                return
            }
        } catch {
            Write-Wrn "Pacote offline do ffmpeg inválido. Tentando métodos online."
        } finally {
            Remove-Item $ffmpegTmp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

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
        Download-File $ffmpegUrl $ffmpegZip -IsZip
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
    try {
        foreach ($sid in @("ETI_SENTINEL_EDGE_AGENT", "ETI_SENTINEL_MEDIAMTX")) {
            try { sc.exe stop $sid | Out-Null } catch {}
        }
    } catch {}

    try {
        $bin = Join-Path $rootDir "bin"
        $sx1 = Join-Path $bin "ETI_SENTINEL_EDGE_AGENT.exe"
        $sx2 = Join-Path $bin "ETI_SENTINEL_MEDIAMTX.exe"
        if (Test-Path $sx1) { try { & $sx1 stop | Out-Null } catch {} }
        if (Test-Path $sx2) { try { & $sx2 stop | Out-Null } catch {} }
    } catch {}

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
    Download-File $url $zip -IsZip
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
    $lines = $lines | Where-Object { $_ -notmatch '^(INGEST_API_URL|COLLECTOR_KEY|CLIENT_ID|ENABLE_STREAMING|ENABLE_RTSP_MONITOR|AGENT_API_BIND|AGENT_API_PORT|EDGE_USE_PYTHONW|EDGE_START_MEDIAMTX|EDGE_EVENT_DEDUPE_SECONDS|EDGE_VIDEOLOSS_CONFIRM_SECONDS|EDGE_RECOVERY_CONFIRM_SECONDS|EDGE_VIDEOLOSS_MIN_SECONDS|EDGE_NOTIFY_RECOVERY|EDGE_SUPPRESS_EVENT_TYPES|STREAM_RESTART_COOLDOWN_SECONDS|STREAM_MAX_RETRIES|STREAM_RETRY_MAX_BACKOFF_SECONDS)=' }
    $lines += "INGEST_API_URL=$ingest"
    $lines += "COLLECTOR_KEY=$key"
    if ($cid) { $lines += "CLIENT_ID=$cid" }
    $lines += "ENABLE_STREAMING=1"
    $lines += "ENABLE_RTSP_MONITOR=0"
    $lines += "AGENT_API_BIND=127.0.0.1"
    $lines += "AGENT_API_PORT=8808"
    $lines += "EDGE_USE_PYTHONW=0"
    $lines += "EDGE_START_MEDIAMTX=0"
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
        $basePy = $script:PythonExe
        if (!$basePy) { $basePy = "python" }
        try { Remove-Item $venv -Recurse -Force -ErrorAction SilentlyContinue } catch {}
        & $basePy -m venv $venv | Out-Null
        if (!(Test-Path $py)) {
            try { Remove-Item $venv -Recurse -Force -ErrorAction SilentlyContinue } catch {}
            & $basePy -m venv $venv | Out-Null
        }
        if (!(Test-Path $py)) { throw "Falha ao criar venv. Verifique Python instalado e permissões." }
    }
    try {
        $installDir = Split-Path -Parent $edgeDir
        $cacheDir = Join-Path $installDir ".pip-cache"
        New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null
        $env:PIP_CACHE_DIR = $cacheDir
    } catch {}
    Write-Inf "Instalando dependências do Edge..."
    if (!(Test-Path $py)) { throw "python.exe da venv não encontrado: $py" }
    $req = Join-Path $edgeDir "requirements.txt"
    if (!(Test-Path $req)) { throw "requirements.txt não encontrado: $req" }
    $wheelhouse = Offline-File "wheelhouse"
    $envFile = Join-Path $edgeDir ".env"
    $aiReq = Join-Path $edgeDir "requirements-ai.txt"
    $aiEnabled = ""
    try {
        if (Test-Path $envFile) { $aiEnabled = (Read-EnvValue $envFile "ENABLE_AI_ANALYTICS").Trim() }
    } catch {}
    $installAI = ((Test-Path $aiReq) -and ($aiEnabled -eq "1" -or $aiEnabled.ToLower() -eq "true"))
    if ($wheelhouse -and (Test-Path $wheelhouse)) {
        & $py -m pip --version | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "pip não disponível na venv." }
        & $py -m pip install --no-index --find-links $wheelhouse -r $req | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar requirements do Edge (offline)." }
        if ($installAI) {
            Write-Inf "Instalando dependências de IA (offline)..."
            & $py -m pip install --no-index --find-links $wheelhouse -r $aiReq | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar requirements de IA (offline)." }
        }
        return
    }
    & $py -m pip install --upgrade pip --no-cache-dir | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar/atualizar pip na venv." }
    & $py -m pip install --no-cache-dir -r $req | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar requirements do Edge." }
    if ($installAI) {
        Write-Inf "Instalando dependências de IA..."
        & $py -m pip install --no-cache-dir -r $aiReq | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar requirements de IA." }
    }
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

$installDirUser = Join-Path $env:LOCALAPPDATA "ETI-SENTINEL"
$installDir = Join-Path $env:ProgramData "ETI-SENTINEL"
if ((Test-Path $installDirUser) -and !(Test-Path $installDir)) {
    try {
        Write-Inf "Migrando instalação antiga para ProgramData..."
        Move-Item -Path $installDirUser -Destination $installDir -Force
    } catch {
        try {
            New-Item -ItemType Directory -Force -Path $installDir | Out-Null
            Copy-Item -Path (Join-Path $installDirUser "*") -Destination $installDir -Recurse -Force
            Remove-Item $installDirUser -Recurse -Force -ErrorAction SilentlyContinue
        } catch {}
    }
}
Write-Inf "Instalação em: $installDir"

try {
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    icacls $installDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
} catch {}

try {
    Ensure-Python
    Ensure-Ffmpeg
    Ensure-MediaMTX

    $existingEnv = Join-Path $installDir "edge-agent\.env"
    $defaultIngest = (Read-EnvValue $existingEnv "INGEST_API_URL").Trim()
    if (!$defaultIngest) { $defaultIngest = "https://eti-sentinel-production.up.railway.app" }
    $defaultKey = (Read-EnvValue $existingEnv "COLLECTOR_KEY").Trim()
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
    if (!$key) { $key = (Read-Host "COLLECTOR_KEY").Trim() }
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
    Ensure-Services $installDir

    $py = Join-Path $edgeDir ".venv\Scripts\python.exe"
    $entry = Join-Path $edgeDir "edge_agent.py"
    Write-Inf "Executando health-check (edge_agent.py --check)..."
    & $py $entry --check
    if ($LASTEXITCODE -ne 0) { throw "Health-check falhou. Verifique logs em $installDir\.logs e $edgeDir\.state" }
    Ensure-Icon $installDir
    Ensure-Shortcuts $installDir

    Write-Ok "Instalado. Edge iniciado e configurado para iniciar com o Windows."
    Write-Inf "Status: http://127.0.0.1:8808/api/status"
} finally {
    if ($script:OfflineTemp) {
        try { Remove-Item $script:OfflineTemp -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
}
