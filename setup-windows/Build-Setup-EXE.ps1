param(
    [string]$OutFile = "./dist/ETI-SENTINEL-Edge-Setup.exe"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$srcScript = Join-Path $PSScriptRoot "Setup-ETI-SENTINEL-Edge-GUI.ps1"
if (!(Test-Path $srcScript)) { throw "Arquivo não encontrado: $srcScript" }

$iexpress = Join-Path $env:WINDIR "System32\iexpress.exe"
if (!(Test-Path $iexpress)) { throw "iexpress.exe não encontrado em $iexpress" }

$outAbs = (Resolve-Path (Join-Path $repoRoot $OutFile) -ErrorAction SilentlyContinue)
if ($outAbs) {
    $outAbs = $outAbs.Path
} else {
    $outAbs = Join-Path $repoRoot $OutFile
}

$outDir = Split-Path -Parent $outAbs
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$tmp = Join-Path $env:TEMP ("eti-iexpress-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
try {
    Copy-Item $srcScript (Join-Path $tmp (Split-Path -Leaf $srcScript)) -Force
    $sed = Join-Path $tmp "setup.sed"

    $friendly = "ETI SENTINEL Edge Setup"
    $app = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File Setup-ETI-SENTINEL-Edge-GUI.ps1"

    $sedText = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=1
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName=$outAbs
FriendlyName=$friendly
AppLaunched=$app
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles

[SourceFiles]
SourceFiles0=$tmp

[SourceFiles0]
%FILE0%=Setup-ETI-SENTINEL-Edge-GUI.ps1

[Strings]
FILE0=Setup-ETI-SENTINEL-Edge-GUI.ps1
"@

    [System.IO.File]::WriteAllText($sed, $sedText, (New-Object System.Text.UTF8Encoding($false)))
    & $iexpress /N $sed | Out-Null
    if (!(Test-Path $outAbs)) { throw "Falha ao gerar o EXE: $outAbs" }
    Write-Host "[OK] Gerado: $outAbs" -ForegroundColor Green
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

