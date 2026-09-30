# Normal-use entry point: builds the frontend if it's stale, then serves everything
# from Uvicorn on http://127.0.0.1:8000 (no separate dev server).
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $repoRoot "frontend"
$dist = Join-Path $frontend "dist"
$src = Join-Path $frontend "src"

function Latest-WriteTime($path) {
    if (-not (Test-Path $path)) { return $null }
    (Get-ChildItem $path -Recurse -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
}

$distTime = Latest-WriteTime $dist
$srcTime = Latest-WriteTime $src
$needsBuild = -not $distTime -or ($srcTime -and $srcTime -gt $distTime)

if ($needsBuild) {
    Write-Host "Building frontend..."
    Push-Location $frontend
    npm run build
    Pop-Location
}

Push-Location (Join-Path $repoRoot "backend")
Start-Job -ScriptBlock { Start-Sleep -Seconds 2; Start-Process "http://127.0.0.1:8000" } | Out-Null
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
