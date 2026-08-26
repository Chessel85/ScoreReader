# packaging/build_installer.ps1
# Optional one-command convenience wrapper that runs the packaging steps
# back to back (M2):
#   1. PyInstaller onedir bundle via VoiceWorker.spec - the hands-free
#      voice-control worker (Ref 19), built as its OWN separate executable
#      (see that spec's own header comment for why). Skipped with a warning,
#      not a failure, if dist\RecallScoreVoiceWorker\vosk\ (or the model
#      dir) turns out missing - voice control is a supplementary feature.
#   2. PyInstaller onedir bundle via RecallScore.spec - Python runtime,
#      PySide6, music21 and the FluidSynth DLLs/SoundFont all embedded, so
#      the installed app needs nothing else (NFR-02 AC-02.3). Also bundles
#      step 1's output (voice_worker/) and the vosk model, if present. The
#      spec itself regenerates version_info.txt from version.txt.
#   3. NSIS (installer.nsi) wraps that bundle into a standard install-wizard
#      .exe - Program Files, Start Menu, Add/Remove Programs entry with a
#      real uninstaller (NFR-02 AC-02.1, M2).
#
# None of these steps need this script - all are runnable directly, IN
# THIS ORDER (RecallScore.spec reads step 1's dist\ output):
#     .venv\Scripts\python.exe -m PyInstaller packaging\VoiceWorker.spec --noconfirm
#     .venv\Scripts\python.exe -m PyInstaller packaging\RecallScore.spec --noconfirm
#     makensis packaging\installer.nsi
# This script just chains them and does a couple of sanity checks first.
#
# Usage:   powershell -File packaging\build_installer.ps1
# Requires: the project .venv (with pyinstaller - installed automatically
# from requirements-build.txt on first run) and NSIS's makensis.exe.
# Output:  dist_installer\RecallScore-Setup-<version>.exe
# Version: edit version.txt (repo root) to change the version number.

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

# --- Version (single source of truth: version.txt, user-maintained) ---
$versionTxtPath = Join-Path $RepoRoot "version.txt"
if (-not (Test-Path $versionTxtPath)) { throw "version.txt not found at $versionTxtPath" }
$Version = (Get-Content $versionTxtPath -TotalCount 1).Trim()
Write-Host "=== Building Recall Score $Version installer ==="

# --- Ensure PyInstaller is available ---
& $Python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing build dependencies (requirements-build.txt)..."
    & $Python -m pip install -r (Join-Path $RepoRoot "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) { throw "Failed to install requirements-build.txt" }
}

# --- Clean previous build output ---
foreach ($dir in @($DistDir, $BuildDir)) {
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# --- Step 1: voice-control worker (must run BEFORE RecallScore.spec, which
# bundles this step's output - see VoiceWorker.spec's own header comment) ---
Write-Host "--- PyInstaller (voice control worker) ---"
& $Python -m PyInstaller (Join-Path $PackagingDir "VoiceWorker.spec") `
    --noconfirm --distpath $DistDir --workpath $BuildDir
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed (VoiceWorker.spec)" }

# --- Step 2: PyInstaller onedir bundle for the main app ---
Write-Host "--- PyInstaller ---"
& $Python -m PyInstaller (Join-Path $PackagingDir "RecallScore.spec") `
    --noconfirm --distpath $DistDir --workpath $BuildDir
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$exePath = Join-Path $DistDir "RecallScore\RecallScore.exe"
if (-not (Test-Path $exePath)) { throw "PyInstaller did not produce $exePath" }

# --- Step 3: NSIS wraps the bundle into an installer ---
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

& $makensisPath (Join-Path $PackagingDir "installer.nsi")
if ($LASTEXITCODE -ne 0) { throw "NSIS build failed" }

$installerPath = Join-Path $OutDir "RecallScore-Setup-$Version.exe"
Write-Host "=== Installer built: $installerPath ==="
