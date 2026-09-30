# Phase 9: one command from a clean checkout to dist\WaymarkSetup-<version>.exe.
#   ./scripts/build-installer.ps1
#
# Requires: uv, npm, and Inno Setup's ISCC.exe on PATH (winget install JRSoftware.InnoSetup).
# Optionally signs with signtool if SIGN_CERT_PATH and SIGN_CERT_PASSWORD are set.
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$packagingDir = Join-Path $repoRoot "packaging"
$distDir = Join-Path $repoRoot "dist"

function Require-Command($name, $hint) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "$name is required but was not found on PATH. $hint"
    }
    return $cmd.Source
}

Write-Host "==> Checking required tools"
$uv = Require-Command "uv" "Install from https://docs.astral.sh/uv/"
$npm = Require-Command "npm" "Install Node.js from https://nodejs.org/"
$iscc = Require-Command "ISCC.exe" "Install Inno Setup: winget install JRSoftware.InnoSetup"

Write-Host "==> Backend tests and lint"
Push-Location $backendDir
try {
    uv run pytest
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }
    uv run ruff check .
    if ($LASTEXITCODE -ne 0) { throw "Ruff check failed." }
} finally {
    Pop-Location
}

Write-Host "==> Building frontend"
Push-Location $frontendDir
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
} finally {
    Pop-Location
}

Write-Host "==> Running PyInstaller (one-folder build)"
Push-Location $backendDir
try {
    uv run pyinstaller (Join-Path $packagingDir "waymark.spec") --distpath $distDir --workpath (Join-Path $repoRoot "build") --noconfirm --clean
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
} finally {
    Pop-Location
}

$exePath = Join-Path $distDir "Waymark\Waymark.exe"
if (-not (Test-Path $exePath)) {
    throw "Expected $exePath after PyInstaller build but it was not found."
}
$version = (Get-Item $exePath).VersionInfo.FileVersion
if (-not $version) {
    # Fall back to the single version source directly if the EXE has no version resource
    # (e.g. it was skipped on a non-Windows dev machine building for CI purposes only).
    $initPy = Join-Path $backendDir "app\__init__.py"
    $match = Select-String -Path $initPy -Pattern '__version__\s*=\s*"([^"]+)"'
    $version = $match.Matches[0].Groups[1].Value
}
Write-Host "==> Building version $version"

Write-Host "==> Running Inno Setup"
& $iscc (Join-Path $packagingDir "waymark.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed." }

$installerPath = Join-Path $distDir "WaymarkSetup-$version.exe"
if (-not (Test-Path $installerPath)) {
    # Inno derives the filename from the built EXE's own version resource, which may format
    # slightly differently (e.g. trailing .0s); fall back to whatever it actually produced.
    $found = Get-ChildItem $distDir -Filter "WaymarkSetup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($found) { $installerPath = $found.FullName }
}
if (-not (Test-Path $installerPath)) {
    throw "Expected an installer under $distDir but none was found."
}

if ($env:SIGN_CERT_PATH -and $env:SIGN_CERT_PASSWORD) {
    $signtool = Require-Command "signtool.exe" "Install the Windows SDK for signtool.exe."
    Write-Host "==> Signing Waymark.exe and the installer"
    & $signtool sign /f $env:SIGN_CERT_PATH /p $env:SIGN_CERT_PASSWORD /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $exePath
    if ($LASTEXITCODE -ne 0) { throw "Signing Waymark.exe failed." }
    & $signtool sign /f $env:SIGN_CERT_PATH /p $env:SIGN_CERT_PASSWORD /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $installerPath
    if ($LASTEXITCODE -ne 0) { throw "Signing the installer failed." }
} else {
    Write-Host "Unsigned build (set SIGN_CERT_PATH and SIGN_CERT_PASSWORD to sign)."
}

$hash = Get-FileHash $installerPath -Algorithm SHA256
Write-Host ""
Write-Host "==> Built $installerPath"
Write-Host "    SHA-256: $($hash.Hash)"
