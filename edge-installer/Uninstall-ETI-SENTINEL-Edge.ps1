$ErrorActionPreference = "Stop"

function Write-Ok([string]$m) { Write-Host "[OK]  $m" -ForegroundColor Green }
function Write-Inf([string]$m) { Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Wrn([string]$m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }

$installDirUser = Join-Path $env:LOCALAPPDATA "ETI-SENTINEL"
$installDir = Join-Path $env:ProgramData "ETI-SENTINEL"
$taskName = "ETI_SENTINEL_EDGE"

try {
    foreach ($sid in @("ETI_SENTINEL_EDGE_AGENT", "ETI_SENTINEL_MEDIAMTX")) {
        try { sc.exe stop $sid | Out-Null } catch {}
    }
} catch {}

try {
    $binDir = Join-Path $installDir "bin"
    $sx1 = Join-Path $binDir "ETI_SENTINEL_EDGE_AGENT.exe"
    $sx2 = Join-Path $binDir "ETI_SENTINEL_MEDIAMTX.exe"
    if (Test-Path $sx1) { try { & $sx1 stop | Out-Null } catch {} }
    if (Test-Path $sx2) { try { & $sx2 stop | Out-Null } catch {} }
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

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -and ($_.CommandLine -like "*\\ETI-SENTINEL\\*") } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$desktop = [Environment]::GetFolderPath("Desktop")
$programs = [Environment]::GetFolderPath("Programs")
Remove-Item (Join-Path $desktop "ETI SENTINEL.lnk") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $programs "ETI SENTINEL") -Recurse -Force -ErrorAction SilentlyContinue

if (Test-Path $installDir) {
    $ans = (Read-Host "Remover pasta $installDir ? (S/N)").Trim().ToUpper()
    if ($ans -eq "S") {
        Remove-Item $installDir -Recurse -Force
        Write-Ok "Pasta removida."
    } else {
        Write-Wrn "Pasta mantida."
    }
}

if ((Test-Path $installDirUser) -and ($installDirUser -ne $installDir)) {
    try {
        $ans2 = (Read-Host "Remover pasta antiga $installDirUser ? (S/N)").Trim().ToUpper()
        if ($ans2 -eq "S") {
            Remove-Item $installDirUser -Recurse -Force
            Write-Ok "Pasta antiga removida."
        } else {
            Write-Wrn "Pasta antiga mantida."
        }
    } catch {}
}

Write-Ok "Desinstalação concluída."
