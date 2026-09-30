<#
.SYNOPSIS
    Restores a snapshot taken by save-my-data.ps1 into a Waymark database.

.DESCRIPTION
    This OVERWRITES a database, so it takes four precautions before it does:

      1. Whatever is currently at the destination is backed up first, timestamped, into
         <repo>/data/snapshots/_pre-restore/ (git-ignored, like everything under data/).
      2. You are asked to confirm, unless -Force is passed.
      3. It refuses to clobber a database belonging to a RUNNING app. The packaged app
         writes %APPDATA%\Waymark\server.json (port + pid) and holds waymark.lock; the
         dev backend answers /api/health on port 8000. Replacing a live SQLite file
         corrupts it, so close Waymark / stop the dev server instead of forcing.
      4. Stale -wal and -shm sidecars next to the replaced .db are removed. A leftover WAL
         belongs to the OLD database - left in place it would either mask the restored
         data or corrupt it outright.

    SCHEMA DRIFT: there is deliberately no migration logic in this script. A snapshot taken
    on an older schema restores fine as-is, because the app runs Alembic `upgrade head` at
    startup - the next launch migrates the restored database forward for you. That is also
    why the .db is the primary artifact and export.json is only a human-readable fallback.

.PARAMETER Name
    Which snapshot to restore, as named by save-my-data.ps1. Default "my-setup".

.PARAMETER Target
    Which database to overwrite:
      dev       <repo>/data/networth.db          (default)
      installed %APPDATA%\Waymark\networth.db   (the packaged app)

.PARAMETER TargetPath
    Restore into an explicit .db path instead of -Target. Intended for testing a snapshot
    against a scratch database (point a backend at its folder with NW_DATA_DIR) without
    touching either real database.

.PARAMETER SnapshotPath
    Restore from an explicit snapshot folder or .db file instead of looking up -Name.

.PARAMETER Force
    Skip the confirmation prompt AND override the running-app refusal. Only use the latter
    when you are certain nothing has the database open.

.EXAMPLE
    ./scripts/restore-my-data.ps1
    Restores "my-setup" into the dev database, after confirming.

.EXAMPLE
    ./scripts/restore-my-data.ps1 -Target installed -Name my-setup
    Restores into the packaged app's database. Close Waymark first.
#>
[CmdletBinding()]
param(
    [string]$Name = "my-setup",
    [ValidateSet("dev", "installed")][string]$Target = "dev",
    [string]$TargetPath,
    [string]$SnapshotPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_waymark-common.ps1")

# ---------------------------------------------------------------- resolve the snapshot
if ($SnapshotPath) {
    if (Test-Path $SnapshotPath -PathType Leaf) {
        $snapshotDb = (Resolve-Path $SnapshotPath).Path
        $snapshotDir = Split-Path -Parent $snapshotDb
    } else {
        $snapshotDir = (Resolve-Path $SnapshotPath).Path
        $snapshotDb = Join-Path $snapshotDir "networth.db"
    }
} else {
    $snapshotDir = Join-Path (Get-WaymarkSnapshotRoot) $Name
    $snapshotDb = Join-Path $snapshotDir "networth.db"
}

if (-not (Test-Path $snapshotDb)) {
    Write-Host "No snapshot database found at: $snapshotDb" -ForegroundColor Red
    $root = Get-WaymarkSnapshotRoot
    if (Test-Path $root) {
        Write-Host "Available snapshots:"
        Get-ChildItem $root -Directory | Where-Object { $_.Name -ne "_pre-restore" } |
            ForEach-Object { Write-Host "  $($_.Name)" }
    }
    throw "Nothing to restore. Take one first with ./scripts/save-my-data.ps1"
}

# ------------------------------------------------------------------ resolve the target
if ($TargetPath) {
    $targetDb = [System.IO.Path]::GetFullPath($TargetPath)
    $targetDir = Split-Path -Parent $targetDb
    $targetLabel = "explicit path"
    $which = "dev"
} else {
    $targetDir = Get-WaymarkDataDir -Which $Target
    $targetDb = Join-Path $targetDir "networth.db"
    $targetLabel = $Target
    $which = $Target
}

Write-Host "Restore plan" -ForegroundColor Cyan
Write-Host "  from: $snapshotDb"
Write-Host "  into: $targetDb  ($targetLabel)"

$manifestPath = Join-Path $snapshotDir "snapshot.json"
if (Test-Path $manifestPath) {
    $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
    Write-Host "  snapshot taken $($manifest.captured_at) from the $($manifest.source) database"
}

# ------------------------------------------------------- guard 1: is an app holding it?
$running = Get-WaymarkRunningApp -DataDir $targetDir -Which $which
if ($running.IsRunning) {
    Write-Host ""
    Write-Host "An app appears to be using the target database right now:" -ForegroundColor Yellow
    foreach ($e in $running.Evidence) { Write-Host "  - $e" }
    if (-not $Force) {
        Write-Host ""
        if ($which -eq "installed") {
            Write-Host "Close Waymark (quit it from the tray/window), then run this again." -ForegroundColor Red
        } else {
            Write-Host "Stop the dev backend (the uvicorn window), then run this again." -ForegroundColor Red
        }
        throw "Refusing to overwrite a database that a running app has open - it would corrupt it."
    }
    Write-Host "  -Force given: proceeding anyway. This can corrupt a live database." -ForegroundColor Red
}

# ------------------------------------------------------------- guard 2: confirm explicitly
if (-not $Force) {
    Write-Host ""
    $answer = Read-Host "Overwrite $targetDb with this snapshot? [y/N]"
    if ($answer -notin @("y", "Y", "yes", "Yes")) {
        Write-Host "Cancelled. Nothing was changed." -ForegroundColor Yellow
        return
    }
}

# ------------------------------------ guard 3: back up whatever is there before replacing
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
$preRestoreDir = Join-Path (Get-WaymarkSnapshotRoot) "_pre-restore"
$backedUpTo = $null
if (Test-Path $targetDb) {
    New-Item -ItemType Directory -Force -Path $preRestoreDir | Out-Null
    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $safeLabel = ($targetLabel -replace '[^A-Za-z0-9._-]', '-')
    # Not named networth-*.db: backup_service prunes that pattern in data/backups, and these
    # pre-restore copies must never be pruned out from under you.
    $backedUpTo = Join-Path $preRestoreDir "pre-restore-$safeLabel-$stamp.db"
    try {
        Invoke-WaymarkHelper -Arguments @("backup", $targetDb, $backedUpTo) | Out-Null
    } catch {
        # Whatever is there is not a readable SQLite database (corrupt, truncated, or not a
        # database at all). Keep a raw byte copy rather than abandoning the restore - there is
        # no consistency to preserve in a file SQLite cannot even open.
        Write-Host "  note: target is not a readable SQLite database; keeping a raw copy instead." -ForegroundColor Yellow
        Copy-Item -Path $targetDb -Destination $backedUpTo -Force
    }
    Write-Host ""
    Write-Host "Backed up the current target database to:" -ForegroundColor Green
    Write-Host "  $backedUpTo"
}

# ------------------------------------------------------------------------- do the restore
Copy-Item -Path $snapshotDb -Destination $targetDb -Force

# Sidecars belong to the database that was just replaced. Delete them, or SQLite will either
# replay the old WAL over the restored pages or refuse to open the file.
foreach ($suffix in @("-wal", "-shm")) {
    $sidecar = "$targetDb$suffix"
    if (Test-Path $sidecar) {
        Remove-Item $sidecar -Force
        Write-Host "  removed stale $(Split-Path -Leaf $sidecar)" -ForegroundColor DarkGray
    }
}

# ----------------------------------------------------------------------------- verify it
$counts = ((Invoke-WaymarkHelper -Arguments @("counts", $targetDb)) -join "`n") | ConvertFrom-Json
Write-Host ""
Write-Host "Restored. Rows now in the target database:" -ForegroundColor Green
foreach ($prop in $counts.PSObject.Properties) {
    if ($prop.Value -gt 0) { Write-Host ("    {0,-28} {1,7}" -f $prop.Name, $prop.Value) }
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
if ($which -eq "installed") {
    Write-Host "  1. Start Waymark. Alembic runs 'upgrade head' at startup, so an older-schema"
    Write-Host "     snapshot is migrated forward automatically."
} else {
    Write-Host "  1. Restart the dev backend (./scripts/dev.ps1, or the uvicorn window) so it"
    Write-Host "     picks up the new file. Alembic runs 'upgrade head' at startup, so an"
    Write-Host "     older-schema snapshot is migrated forward automatically."
}
Write-Host "  2. Check the dashboard looks right."
if ($backedUpTo) {
    Write-Host "  3. If something is wrong, the previous database is still at:"
    Write-Host "     $backedUpTo"
}
