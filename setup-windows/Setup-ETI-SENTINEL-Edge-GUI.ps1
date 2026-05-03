param(
    [string]$Ingest = "https://eti-sentinel-production.up.railway.app",
    [string]$ClientId = "",
    [string]$CollectorKey = "",
    [switch]$Update
)

$ErrorActionPreference = "Stop"

function Test-Admin {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        $p = New-Object Security.Principal.WindowsPrincipal($id)
        return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch {
        return $false
    }
}

function Relaunch-Admin {
    if (Test-Admin) { return $false }
    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PSCommandPath)
    if ($Ingest) { $args += @("-Ingest", $Ingest) }
    if ($ClientId) { $args += @("-ClientId", $ClientId) }
    if ($CollectorKey) { $args += @("-CollectorKey", $CollectorKey) }
    if ($Update) { $args += "-Update" }
    Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $args | Out-Null
    return $true
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
            if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
                Start-BitsTransfer -Source $url -Destination $dest -ErrorAction Stop
            } else {
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

if (Relaunch-Admin) { exit 0 }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "ETI SENTINEL - Setup (Online)"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(620, 520)
$form.MaximizeBox = $false
$form.FormBorderStyle = "FixedDialog"

$fontLabel = New-Object System.Drawing.Font("Segoe UI", 9)
$fontMono = New-Object System.Drawing.Font("Consolas", 9)

$lblInfo = New-Object System.Windows.Forms.Label
$lblInfo.AutoSize = $true
$lblInfo.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$lblInfo.Text = "Instalador Online do ETI SENTINEL Edge"
$lblInfo.Location = New-Object System.Drawing.Point(16, 14)
$form.Controls.Add($lblInfo)

$lblIngest = New-Object System.Windows.Forms.Label
$lblIngest.AutoSize = $true
$lblIngest.Font = $fontLabel
$lblIngest.Text = "INGEST_API_URL"
$lblIngest.Location = New-Object System.Drawing.Point(16, 52)
$form.Controls.Add($lblIngest)

$txtIngest = New-Object System.Windows.Forms.TextBox
$txtIngest.Font = $fontMono
$txtIngest.Size = New-Object System.Drawing.Size(570, 24)
$txtIngest.Location = New-Object System.Drawing.Point(16, 72)
$txtIngest.Text = $Ingest
$form.Controls.Add($txtIngest)

$lblClient = New-Object System.Windows.Forms.Label
$lblClient.AutoSize = $true
$lblClient.Font = $fontLabel
$lblClient.Text = "CLIENT_ID"
$lblClient.Location = New-Object System.Drawing.Point(16, 108)
$form.Controls.Add($lblClient)

$txtClient = New-Object System.Windows.Forms.TextBox
$txtClient.Font = $fontMono
$txtClient.Size = New-Object System.Drawing.Size(180, 24)
$txtClient.Location = New-Object System.Drawing.Point(16, 128)
$txtClient.Text = $ClientId
$form.Controls.Add($txtClient)

$lblKey = New-Object System.Windows.Forms.Label
$lblKey.AutoSize = $true
$lblKey.Font = $fontLabel
$lblKey.Text = "COLLECTOR_KEY"
$lblKey.Location = New-Object System.Drawing.Point(212, 108)
$form.Controls.Add($lblKey)

$txtKey = New-Object System.Windows.Forms.TextBox
$txtKey.Font = $fontMono
$txtKey.Size = New-Object System.Drawing.Size(374, 24)
$txtKey.Location = New-Object System.Drawing.Point(212, 128)
$txtKey.Text = $CollectorKey
$form.Controls.Add($txtKey)

$chkUpdate = New-Object System.Windows.Forms.CheckBox
$chkUpdate.AutoSize = $true
$chkUpdate.Font = $fontLabel
$chkUpdate.Text = "Update (reinstalar/atualizar Edge existente)"
$chkUpdate.Location = New-Object System.Drawing.Point(16, 164)
$chkUpdate.Checked = [bool]$Update
$form.Controls.Add($chkUpdate)

$btnInstall = New-Object System.Windows.Forms.Button
$btnInstall.Text = "Instalar"
$btnInstall.Size = New-Object System.Drawing.Size(120, 30)
$btnInstall.Location = New-Object System.Drawing.Point(466, 158)
$form.Controls.Add($btnInstall)

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Minimum = 0
$bar.Maximum = 100
$bar.Value = 0
$bar.Size = New-Object System.Drawing.Size(570, 18)
$bar.Location = New-Object System.Drawing.Point(16, 202)
$form.Controls.Add($bar)

$txtLog = New-Object System.Windows.Forms.TextBox
$txtLog.Multiline = $true
$txtLog.ScrollBars = "Vertical"
$txtLog.ReadOnly = $true
$txtLog.Font = $fontMono
$txtLog.Size = New-Object System.Drawing.Size(570, 250)
$txtLog.Location = New-Object System.Drawing.Point(16, 230)
$form.Controls.Add($txtLog)

$script:InstallJob = $null
$script:InstallTimer = $null
$script:LogFile = Join-Path $env:TEMP ("eti-sentinel-setup-" + [Guid]::NewGuid().ToString("N") + ".log")

try {
    [System.IO.File]::WriteAllText($script:LogFile, "", (New-Object System.Text.UTF8Encoding($false)))
} catch {}

function Append-Log([string]$line) {
    if (!$line) { return }
    try {
        [System.IO.File]::AppendAllText($script:LogFile, $line + "`r`n", (New-Object System.Text.UTF8Encoding($false)))
    } catch {}
    $form.BeginInvoke([Action] {
        $txtLog.AppendText($line + "`r`n")
        $txtLog.SelectionStart = $txtLog.Text.Length
        $txtLog.ScrollToCaret()
    }) | Out-Null
}

function Set-Progress([int]$v) {
    $vv = [Math]::Max(0, [Math]::Min(100, $v))
    $form.BeginInvoke([Action] { $bar.Value = $vv }) | Out-Null
}

$btnInstall.Add_Click({
    try {
        $ing = ("" + $txtIngest.Text).Trim()
        $cid = ("" + $txtClient.Text).Trim()
        $ck = ("" + $txtKey.Text).Trim()
        if (!$ing) { [System.Windows.Forms.MessageBox]::Show("Informe INGEST_API_URL") | Out-Null; return }
        if (!$ck) { [System.Windows.Forms.MessageBox]::Show("Informe COLLECTOR_KEY") | Out-Null; return }
        Set-Progress 2
        $btnInstall.Enabled = $false
        $chkUpdate.Enabled = $false
        $txtIngest.Enabled = $false
        $txtClient.Enabled = $false
        $txtKey.Enabled = $false

        if ($script:InstallTimer) {
            try { $script:InstallTimer.Stop() } catch {}
            $script:InstallTimer = $null
        }
        if ($script:InstallJob) {
            try { Remove-Job -Job $script:InstallJob -Force -ErrorAction SilentlyContinue } catch {}
            $script:InstallJob = $null
        }

        $script:InstallJob = Start-Job -ScriptBlock {
            param($ing, $cid, $ck, $doUpdate)
        $repoZip = "https://github.com/etitecnologies-sketch/ETI-SENTINEL/archive/refs/heads/main.zip"
        $tmp = Join-Path $env:TEMP ("eti-sentinel-setup-" + [Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path $tmp | Out-Null
        $zip = Join-Path $tmp "main.zip"
        $extract = Join-Path $tmp "src"
        New-Item -ItemType Directory -Force -Path $extract | Out-Null

        function Test-ZipFile([string]$path) {
            try {
                if (!(Test-Path $path)) { return $false }
                $fs = [System.IO.File]::OpenRead($path)
                try {
                    $zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Read, $false)
                    try { return ($zip.Entries.Count -ge 0) } finally { $zip.Dispose() }
                } finally { $fs.Dispose() }
            } catch { return $false }
        }
        function Download-File([string]$url, [string]$dest, [switch]$IsZip) {
            $destDir = Split-Path -Parent $dest
            if ($destDir) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
            for ($i = 1; $i -le 3; $i++) {
                try {
                    if (Test-Path $dest) { Remove-Item $dest -Force -ErrorAction SilentlyContinue }
                    if (Get-Command Start-BitsTransfer -ErrorAction SilentlyContinue) {
                        Start-BitsTransfer -Source $url -Destination $dest -ErrorAction Stop
                    } else {
                        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing -Headers @{"Cache-Control"="no-cache";"Pragma"="no-cache"} -ErrorAction Stop
                    }
                    if (!(Test-Path $dest)) { throw "download_missing" }
                    $len = (Get-Item $dest).Length
                    if ($len -lt 1024) { throw "download_too_small:$len" }
                    if ($IsZip) { if (!(Test-ZipFile $dest)) { throw "zip_invalid" } }
                    return
                } catch {
                    if ($i -eq 3) { throw }
                    Start-Sleep -Seconds (2 * $i)
                }
            }
        }

        Write-Output "[INFO] Baixando instalador (main.zip)..."
        Download-File $repoZip $zip -IsZip
        Write-Output "[INFO] Extraindo..."
        Expand-Archive -Path $zip -DestinationPath $extract -Force
        $src = Get-ChildItem -Path $extract -Directory | Where-Object { $_.Name -like "ETI-SENTINEL-*" } | Select-Object -First 1
        if (!$src) { throw "Falha ao localizar pasta extraída." }
        $setup = Join-Path $src.FullName "edge-installer\Setup-ETI-SENTINEL-Edge.ps1"
        if (!(Test-Path $setup)) { throw "Setup-ETI-SENTINEL-Edge.ps1 não encontrado." }

        $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $setup, "-Ingest", $ing, "-CollectorKey", $ck)
        if ($cid) { $args += @("-ClientId", $cid) }
        if ($doUpdate) { $args += "-Update" }
        Write-Output "[INFO] Executando instalador interno..."

        $p = Start-Process -FilePath "powershell.exe" -ArgumentList $args -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "Falha na instalação (ExitCode=$($p.ExitCode))" }
            Write-Output "[OK] Instalado com sucesso."
        } -ArgumentList @($ing, $cid, $ck, $chkUpdate.Checked)

        $script:InstallTimer = New-Object System.Windows.Forms.Timer
        $script:InstallTimer.Interval = 400
        $script:InstallTimer.Add_Tick({
            $job = $script:InstallJob
            if (!$job) {
                try { $script:InstallTimer.Stop() } catch {}
                $btnInstall.Enabled = $true
                $chkUpdate.Enabled = $true
                $txtIngest.Enabled = $true
                $txtClient.Enabled = $true
                $txtKey.Enabled = $true
                Set-Progress 0
                Append-Log "[ERR] Job de instalação não foi criado."
                return
            }

            $ev = @()
            $out = Receive-Job -Job $job -Keep -ErrorAction SilentlyContinue -ErrorVariable ev
            foreach ($l in $out) { Append-Log ("" + $l) }
            foreach ($e in ($ev | Where-Object { $_ })) { Append-Log ("[ERR] " + ($e.ToString())) }
            if ($job.State -eq "Running") {
                if ($bar.Value -lt 85) { Set-Progress ($bar.Value + 1) }
                return
            }

            try { $script:InstallTimer.Stop() } catch {}
            try {
                $err = $null
                try { $err = Receive-Job -Job $job -ErrorAction SilentlyContinue } catch {}
                if ($job.State -eq "Failed") {
                    Append-Log "[ERR] Falha na instalação"
                    if ($err) { foreach ($e in $err) { Append-Log ("[ERR] " + $e.ToString()) } }
                    Append-Log ("[INFO] Log salvo em: " + $script:LogFile)
                    [System.Windows.Forms.MessageBox]::Show("Falha na instalação. Log salvo em:`r`n$($script:LogFile)") | Out-Null
                    Set-Progress 0
                } else {
                    Set-Progress 100
                    Append-Log ("[INFO] Log salvo em: " + $script:LogFile)
                    [System.Windows.Forms.MessageBox]::Show("Instalação concluída. Log salvo em:`r`n$($script:LogFile)") | Out-Null
                }
            } finally {
                try { Remove-Job -Job $job -Force -ErrorAction SilentlyContinue } catch {}
                $script:InstallJob = $null
                $btnInstall.Enabled = $true
                $chkUpdate.Enabled = $true
                $txtIngest.Enabled = $true
                $txtClient.Enabled = $true
                $txtKey.Enabled = $true
            }
        })
        $script:InstallTimer.Start()
    } catch {
        Append-Log ("[ERR] " + $_.Exception.Message)
        try { [System.Windows.Forms.MessageBox]::Show("Falha ao iniciar a instalação. Veja o log.") | Out-Null } catch {}
        $btnInstall.Enabled = $true
        $chkUpdate.Enabled = $true
        $txtIngest.Enabled = $true
        $txtClient.Enabled = $true
        $txtKey.Enabled = $true
        Set-Progress 0
    }
})

[void]$form.ShowDialog()

