# Shared helpers for save-my-data.ps1 / restore-my-data.ps1.
# Dot-source this; it defines functions only and performs no actions of its own.

function Get-WaymarkRepoRoot {
    Split-Path -Parent $PSScriptRoot
}

function Get-WaymarkPython {
    # Standard library only, so any Python on PATH will do; fall back to the backend's uv env.
    foreach ($candidate in @("python", "py", "python3")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) { return @($cmd.Source) }
    }
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return @("uv", "run", "--project", (Join-Path (Get-WaymarkRepoRoot) "backend"), "python")
    }
    throw "No Python interpreter found on PATH (tried python, py, python3, uv)."
}

function Invoke-WaymarkHelper {
    # Runs scripts/_waymark_snapshot.py with the given arguments; throws on non-zero exit.
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $helper = Join-Path $PSScriptRoot "_waymark_snapshot.py"
    # @() because PowerShell unrolls a single-element array on return.
    $python = @(Get-WaymarkPython)
    $exe = $python[0]
    $argList = @()
    if ($python.Count -gt 1) { $argList += $python[1..($python.Count - 1)] }
    $argList += $helper
    $argList += $Arguments

    $output = & $exe @argList
    if ($LASTEXITCODE -ne 0) {
        throw "snapshot helper failed ($($Arguments[0])): $output"
    }
    return $output
}

function Get-WaymarkDataDir {
    # 'dev'       -> <repo>/data                (matches paths.data_dir() when not frozen)
    # 'installed' -> %APPDATA%\Waymark         (matches paths.data_dir() when frozen), or
    #                %APPDATA%\Passbook if an install from before the rename hasn't moved it yet
    param([Parameter(Mandatory = $true)][ValidateSet("dev", "installed")][string]$Which)

    if ($Which -eq "installed") {
        $current = Join-Path $env:APPDATA "Waymark"
        $legacy = Join-Path $env:APPDATA "Passbook"
        if (-not (Test-Path $current) -and (Test-Path $legacy)) { return $legacy }
        return $current
    }
    return (Join-Path (Get-WaymarkRepoRoot) "data")
}

function Get-WaymarkSnapshotRoot {
    # Always inside the repo's data/ directory, which .gitignore excludes wholesale.
    Join-Path (Get-WaymarkRepoRoot) "data\snapshots"
}

function Test-WaymarkHealth {
    param([Parameter(Mandatory = $true)][int]$Port)
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2 -UseBasicParsing
        return $resp.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-WaymarkRunningApp {
    <#
      Detects an app process that currently holds the database in $DataDir open.

      Returns a PSCustomObject with .IsRunning plus whatever evidence was found:
        - Port    : from server.json (packaged app) or the dev default, confirmed by /api/health
        - Pid     : from server.json, confirmed to be a live process
        - LockHeld: waymark.lock could not be opened exclusively, i.e. someone holds it

      The packaged app writes server.json + holds waymark.lock (app/launcher.py). The dev
      uvicorn server does neither, so for 'dev' we fall back to probing port 8000.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$DataDir,
        [Parameter(Mandatory = $true)][ValidateSet("dev", "installed")][string]$Which
    )

    $info = [PSCustomObject]@{
        IsRunning = $false
        Port      = $null
        Pid       = $null
        LockHeld  = $false
        Evidence  = @()
    }

    $serverJson = Join-Path $DataDir "server.json"
    if (Test-Path $serverJson) {
        try {
            $meta = Get-Content $serverJson -Raw | ConvertFrom-Json
            if ($meta.pid) {
                $proc = Get-Process -Id $meta.pid -ErrorAction SilentlyContinue
                if ($proc) {
                    $info.IsRunning = $true
                    $info.Pid = $meta.pid
                    $info.Evidence += "server.json pid $($meta.pid) is alive ($($proc.ProcessName))"
                }
            }
            if ($meta.port -and (Test-WaymarkHealth -Port ([int]$meta.port))) {
                $info.IsRunning = $true
                $info.Port = [int]$meta.port
                $info.Evidence += "/api/health answered on port $($meta.port)"
            }
        } catch {
            $info.Evidence += "server.json present but unreadable: $($_.Exception.Message)"
        }
    }

    # passbook.lock: an app from before the rename to Waymark.
    foreach ($lock in @((Join-Path $DataDir "waymark.lock"), (Join-Path $DataDir "passbook.lock"))) {
        if (-not (Test-Path $lock)) { continue }
        try {
            # FileShare.None fails while any other process still holds the file open.
            $fs = [System.IO.File]::Open($lock, "Open", "ReadWrite", "None")
            $fs.Close()
        } catch {
            $info.IsRunning = $true
            $info.LockHeld = $true
            $info.Evidence += "$(Split-Path -Leaf $lock) is held by another process"
        }
    }

    # The port-8000 fallback only makes sense when the directory really is the dev data dir.
    # Restoring into a scratch folder must not be blocked just because a dev server is up.
    $isDevDataDir = $false
    try {
        $devDir = [System.IO.Path]::GetFullPath((Get-WaymarkDataDir -Which "dev"))
        $isDevDataDir = ([System.IO.Path]::GetFullPath($DataDir).TrimEnd('\') -ieq $devDir.TrimEnd('\'))
    } catch { $isDevDataDir = $false }

    if ($Which -eq "dev" -and $isDevDataDir -and -not $info.Port) {
        if (Test-WaymarkHealth -Port 8000) {
            $info.IsRunning = $true
            $info.Port = 8000
            $info.Evidence += "dev backend answered /api/health on port 8000"
        }
    }

    return $info
}

function Get-WaymarkExportJson {
    # Pulls GET /api/export from a running app, so the JSON dump matches export_service
    # exactly. Returns $null when no app is reachable (caller falls back to a direct dump).
    param([Parameter(Mandatory = $true)][int]$Port)
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/export" -TimeoutSec 20 -UseBasicParsing
        if ($resp.StatusCode -eq 200) { return $resp.Content }
    } catch {
        return $null
    }
    return $null
}
