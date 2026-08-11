# packaging/build_installer.ps1
# Builds the Windows installer for Recall Score end to end (M2):
#   1. PyInstaller onedir bundle via RecallScore.spec - Python runtime,
#      PySide6, music21 and the FluidSynth DLLs/SoundFont all embedded, so
#      the installed app needs nothing else (NFR-02 AC-02.3).
#   2. NSIS (installer.nsi) wraps that bundle into a standard install-wizard
#      .exe - Program Files, Start Menu, Add/Remove Programs entry with a
#      real uninstaller (NFR-02 AC-02.1, M2).
#
# Usage:   powershell -File packaging\build_installer.ps1
# Requires: the project .venv (with pyinstaller - installed automatically
# from requirements-build.txt on first run) and NSIS's makensis.exe.
# Output:  dist_installer\RecallScore-Setup-<version>.exe

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PackagingDir = $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$DistDir = Join-Path $RepoRoot "dist"
$BuildDir = Join-Path $RepoRoot "build"
$OutDir = Join-Path $RepoRoot "dist_installer"

if (-not (Test-Path $Python)) {
    throw "Expected a project venv at $Python - see CLAUDE.md for setup (.venv checked out, not tracked)."
}

foreach ($native in @("bin", "soundfonts")) {
    $p = Join-Path $RepoRoot $native
    if (-not (Test-Path $p)) {
        throw "$p is missing - the FluidSynth DLLs/SoundFont are gitignored local binaries (see CLAUDE.md, 'Local binaries'); restore them before packaging or the built app will silently run with no audio."
    }
}

# --- Version (single source of truth: version.py) ---
$versionMatch = Select-String -Path (Join-Path $RepoRoot "version.py") -Pattern '__version__\s*=\s*"([\d.]+)"'
if (-not $versionMatch) { throw "Could not read __version__ from version.py" }
$Version = $versionMatch.Matches[0].Groups[1].Value
$versionOctets = @($Version -split '\.') + @("0", "0", "0", "0")
$FileVersTuple = ($versionOctets[0..3] -join ", ")
Write-Host "=== Building Recall Score $Version installer ==="

# --- Ensure PyInstaller is available ---
& $Python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing build dependencies (requirements-build.txt)..."
    & $Python -m pip install -r (Join-Path $RepoRoot "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) { throw "Failed to install requirements-build.txt" }
}

# --- Windows exe version resource (regenerated fresh every build - not tracked in git) ---
$versionInfoPath = Join-Path $PackagingDir "version_info.txt"
@"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($FileVersTuple),
    prodvers=($FileVersTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'FileDescription', u'Recall Score - accessible music score and tab viewer'),
        StringStruct(u'FileVersion', u'$Version'),
        StringStruct(u'InternalName', u'RecallScore'),
        StringStruct(u'OriginalFilename', u'RecallScore.exe'),
        StringStruct(u'ProductName', u'Recall Score'),
        StringStruct(u'ProductVersion', u'$Version')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Path $versionInfoPath -Encoding UTF8

# --- Clean previous build output ---
foreach ($dir in @($DistDir, $BuildDir)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# --- Step 1: PyInstaller onedir bundle ---
Write-Host "--- PyInstaller ---"
& $Python -m PyInstaller (Join-Path $PackagingDir "RecallScore.spec") `
    --noconfirm --distpath $DistDir --workpath $BuildDir
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$exePath = Join-Path $DistDir "RecallScore\RecallScore.exe"
if (-not (Test-Path $exePath)) { throw "PyInstaller did not produce $exePath" }

# --- Step 2: NSIS wraps the bundle into an installer ---
Write-Host "--- NSIS ---"
$makensisPath = $null
$cmd = Get-Command makensis.exe -ErrorAction SilentlyContinue
if ($cmd) {
    $makensisPath = $cmd.Source
} else {
    foreach ($candidate in @(
        "C:\Program Files (x86)\NSIS\makensis.exe",
        "C:\Program Files\NSIS\makensis.exe"
    )) {
        if (Test-Path $candidate) { $makensisPath = $candidate; break }
    }
}
if (-not $makensisPath) {
    throw "makensis.exe not found - install NSIS (https://nsis.sourceforge.io/) or add it to PATH."
}

$nsisArgs = @(
    "/DAPP_VERSION=$Version",
    "/DDIST_DIR=$(Join-Path $DistDir 'RecallScore')",
    "/DOUT_DIR=$OutDir"
)
$iconPath = Join-Path $PackagingDir "icon.ico"
if (Test-Path $iconPath) { $nsisArgs += "/DICON_PATH=$iconPath" }

& $makensisPath @nsisArgs (Join-Path $PackagingDir "installer.nsi")
if ($LASTEXITCODE -ne 0) { throw "NSIS build failed" }

$installerPath = Join-Path $OutDir "RecallScore-Setup-$Version.exe"
Write-Host "=== Installer built: $installerPath ==="
