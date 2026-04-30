$ErrorActionPreference = "Stop"

function Write-Ok([string]$m) { Write-Host "[OK]  $m" -ForegroundColor Green }
function Write-Inf([string]$m) { Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Write-Wrn([string]$m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }

$installDir = Join-Path $env:LOCALAPPDATA "ETI-SENTINEL"
$taskName = "ETI_SENTINEL_EDGE"

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

Write-Ok "Desinstalação concluída."
