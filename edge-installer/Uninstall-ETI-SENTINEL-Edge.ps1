param(
    [switch]$Silent
)

$ErrorActionPreference = "Stop"

function Write-Ok([string]$m)  { Write-Host "[OK]  $m" -ForegroundColor Green }
function Write-Inf([string]$m) { Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Wrn([string]$m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err([string]$m) { Write-Host "[ERR] $m" -ForegroundColor Red }

function Test-Admin {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $p  = New-Object Security.Principal.WindowsPrincipal($id)
        return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch { return $false }
}

# Eleva automaticamente para admin se necessário — igual ao instalador
if (!(Test-Admin)) {
    Write-Wrn "Este desinstalador precisa ser executado como Administrador."
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    if ($Silent) { $argList += "-Silent" }
    try {
        Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argList | Out-Null
        exit 0
    } catch {
        throw "Falha ao elevar privilégios. Reexecute como Administrador."
    }
}

$installDirUser = Join-Path $env:LOCALAPPDATA "ETI-SENTINEL"
$installDir     = Join-Path $env:ProgramData "ETI-SENTINEL"
$taskName       = "ETI_SENTINEL_EDGE"

try {
    foreach ($sid in @("ETI_SENTINEL_EDGE_AGENT", "ETI_SENTINEL_MEDIAMTX")) {
        try { sc.exe stop $sid | Out-Null } catch {}
    }
} catch {}

try {
    $binDir = Join-Path $installDir "bin"
    $sx1 = Join-Path $binDir "ETI_SENTINEL_EDGE_AGENT.exe"
    $sx2 = Join-Path $binDir "ETI_SENTINEL_MEDIAMTX.exe"
    if (Test-Path $sx1) { try { & $sx1 stop      | Out-Null } catch {} }
    if (Test-Path $sx2) { try { & $sx2 stop      | Out-Null } catch {} }
    if (Test-Path $sx1) { try { & $sx1 uninstall | Out-Null } catch {} }
    if (Test-Path $sx2) { try { & $sx2 uninstall | Out-Null } catch {} }
} catch {}

try {
    Get-ScheduledTask -TaskName "ETI_SENTINEL_*" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-ScheduledTask -TaskName $_.TaskName -ErrorAction SilentlyContinue }
} catch {}
try {
    Get-ScheduledTask -TaskName "ETI_SENTINEL_*" -ErrorAction SilentlyContinue |
        ForEach-Object { Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null }
} catch {}

# Encerra processos residuais — falha silenciosa se não houver permissão
try {
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -and ($_.CommandLine -like "*\\ETI-SENTINEL\\*") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {
    Write-Wrn "Não foi possível encerrar todos os processos: $($_.Exception.Message)"
}

$desktop  = [Environment]::GetFolderPath("Desktop")
$programs = [Environment]::GetFolderPath("Programs")
Remove-Item (Join-Path $desktop "ETI SENTINEL.lnk") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $programs "ETI SENTINEL")    -Recurse -Force -ErrorAction SilentlyContinue

if (Test-Path $installDir) {
    # Lê versão do manifest.json antes de remover qualquer coisa
    $manifestPath = Join-Path $installDir "manifest.json"
    $versionInfo  = "desconhecida"
    if (Test-Path $manifestPath) {
        try {
            $mf = Get-Content $manifestPath -Raw | ConvertFrom-Json
            $versionInfo = "bundle $($mf.bundle_version) (build $($mf.build_date))"
        } catch {}
    }

    # Grava log de auditoria antes de qualquer remoção
    $auditPath = Join-Path $env:TEMP "ETI-SENTINEL-uninstall.log"
    @(
        "=== ETI SENTINEL — Log de Desinstalação ==="
        "Data/hora : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        "Usuário   : $env:USERNAME"
        "Versão    : $versionInfo"
        "Pasta     : $installDir"
        ""
        "Itens removidos:"
        "  - Serviços: ETI_SENTINEL_EDGE_AGENT, ETI_SENTINEL_MEDIAMTX"
        "  - Tarefas agendadas: ETI_SENTINEL_*"
        "  - Atalhos da área de trabalho e menu Iniciar"
    ) | Out-File -FilePath $auditPath -Encoding UTF8 -Force
    Write-Inf "Log de auditoria salvo em: $auditPath"

    $ans = if ($Silent) { "S" } else { (Read-Host "Remover pasta $installDir ? (S/N)").Trim().ToUpper() }
    if ($ans -eq "S") {
        Remove-Item $installDir -Recurse -Force
        Write-Ok "Pasta removida."
        Add-Content -Path $auditPath -Value "  - Pasta principal: REMOVIDA"
    } else {
        Write-Wrn "Pasta mantida."

        # Oferece remoção granular das partes que mais ocupam espaço
        $pyDir = Join-Path $installDir "python"
        if (Test-Path $pyDir) {
            $ansPy = if ($Silent) { "N" } else {
                (Read-Host "Remover Python instalado pelo ETI SENTINEL em $pyDir (~100MB)? (S/N)").Trim().ToUpper()
            }
            if ($ansPy -eq "S") {
                Remove-Item $pyDir -Recurse -Force -ErrorAction SilentlyContinue
                Write-Ok "Pasta Python removida."
                Add-Content -Path $auditPath -Value "  - Pasta Python: REMOVIDA"
            }
        }

        $ffmpegExe = Join-Path $installDir "bin\ffmpeg.exe"
        if (Test-Path $ffmpegExe) {
            $ansFF = if ($Silent) { "N" } else {
                (Read-Host "Remover ffmpeg/ffprobe instalados pelo ETI SENTINEL em $installDir\bin\ ? (S/N)").Trim().ToUpper()
            }
            if ($ansFF -eq "S") {
                Remove-Item (Join-Path $installDir "bin\ffmpeg.exe")  -Force -ErrorAction SilentlyContinue
                Remove-Item (Join-Path $installDir "bin\ffprobe.exe") -Force -ErrorAction SilentlyContinue
                Write-Ok "ffmpeg/ffprobe removidos."
                Add-Content -Path $auditPath -Value "  - ffmpeg/ffprobe: REMOVIDOS"
            }
        }
    }
}

if ((Test-Path $installDirUser) -and ($installDirUser -ne $installDir)) {
    try {
        $ans2 = if ($Silent) { "S" } else {
            (Read-Host "Remover pasta antiga $installDirUser ? (S/N)").Trim().ToUpper()
        }
        if ($ans2 -eq "S") {
            Remove-Item $installDirUser -Recurse -Force
            Write-Ok "Pasta antiga removida."
        } else {
            Write-Wrn "Pasta antiga mantida."
        }
    } catch {}
}

Write-Ok "Desinstalação concluída."
