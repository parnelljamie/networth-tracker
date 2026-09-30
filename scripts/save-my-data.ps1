<#
.SYNOPSIS
    Saves your real Waymark setup as a named, restorable snapshot.

.DESCRIPTION
    Captures two artifacts per snapshot, so a reset or reinstall never costs you a
    re-typing session:

      networth.db   a real SQLite **online backup** (sqlite3's backup API, the same one
                    backend/app/services/backup_service.py uses). Safe to take while the
                    app is running and writing; a plain file copy of a live WAL database
                    is not. This is what restore-my-data.ps1 puts back.
      export.json   the human-readable full row dump. Taken from the running app's
                    GET /api/export (export_service.export_all) when one is reachable,
                    otherwise read straight out of the snapshot database. This is the
                    fallback that stays readable if a future schema change ever makes an
                    old .db awkward to restore.
      snapshot.json a manifest: when, from where, and row counts per table.

    PRIVACY: snapshots contain your real financial data. They are written under
    <repo>/data/snapshots/, and .gitignore excludes data/ wholesale ("personal financial
    data never goes into git"). Never move a snapshot outside an ignored location.

.PARAMETER Name
    Snapshot name, so you can keep several. Defaults to "my-setup", which is also the
    default restore-my-data.ps1 looks for.

.PARAMETER Source
    Which database to snapshot:
      dev       <repo>/data/networth.db          (default)
      installed %APPDATA%\Waymark\networth.db   (the packaged app)
    The installed app may well be running - that is fine, the online-backup API handles
    a live database safely.

.EXAMPLE
    ./scripts/save-my-data.ps1
    Snapshots the dev database as "my-setup".

.EXAMPLE
    ./scripts/save-my-data.ps1 -Source installed -Name before-reinstall
#>
[CmdletBinding()]
param(
    [string]$Name = "my-setup",
    [ValidateSet("dev", "installed")][string]$Source = "dev"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_waymark-common.ps1")

if ($Name -notmatch '^[A-Za-z0-9._-]+$') {
    throw "-Name must contain only letters, digits, dot, dash or underscore (got '$Name')."
}

$sourceDir = Get-WaymarkDataDir -Which $Source
$sourceDb = Join-Path $sourceDir "networth.db"
if (-not (Test-Path $sourceDb)) {
    throw "No database found at $sourceDb. Run the $Source app at least once first."
}

$snapshotDir = Join-Path (Get-WaymarkSnapshotRoot) $Name
$snapshotDb = Join-Path $snapshotDir "networth.db"
$exportPath = Join-Path $snapshotDir "export.json"
$manifestPath = Join-Path $snapshotDir "snapshot.json"

Write-Host "Snapshotting $Source database" -ForegroundColor Cyan
Write-Host "  source: $sourceDb"

$running = Get-WaymarkRunningApp -DataDir $sourceDir -Which $Source
if ($running.IsRunning) {
    Write-Host "  note:   an app is currently using this database - taking an online backup (safe)."
    foreach ($e in $running.Evidence) { Write-Host "          - $e" -ForegroundColor DarkGray }
}

New-Item -ItemType Directory -Force -Path $snapshotDir | Out-Null

# 1. Online backup of the database.
Invoke-WaymarkHelper -Arguments @("backup", $sourceDb, $snapshotDb) | Out-Null

# 2. JSON dump - prefer the running app's own export endpoint.
$exportSource = $null
if ($running.Port) {
    $json = Get-WaymarkExportJson -Port $running.Port
    if ($json) {
        [System.IO.File]::WriteAllText($exportPath, $json)
        $exportSource = "GET /api/export on port $($running.Port)"
    }
}
if (-not $exportSource) {
    Invoke-WaymarkHelper -Arguments @("dump", $snapshotDb, $exportPath) | Out-Null
    $exportSource = "direct SQLite dump of the snapshot (no running app to ask)"
}

# 3. Row counts, read back out of the snapshot itself so they describe what was captured.
$countsJson = (Invoke-WaymarkHelper -Arguments @("counts", $snapshotDb)) -join "`n"
$counts = $countsJson | ConvertFrom-Json

$manifest = [ordered]@{
    name          = $Name
    source        = $Source
    source_db     = $sourceDb
    captured_at   = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    method        = "sqlite3 online backup API"
    export_source = $exportSource
    row_counts    = $counts
}
[System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 5))

Write-Host ""
Write-Host "Snapshot written to:" -ForegroundColor Green
Write-Host "  $snapshotDir"
Write-Host "    networth.db   $([math]::Round((Get-Item $snapshotDb).Length / 1KB, 1)) KB   (online backup)"
Write-Host "    export.json   $([math]::Round((Get-Item $exportPath).Length / 1KB, 1)) KB   ($exportSource)"
Write-Host "    snapshot.json manifest with row counts"
Write-Host ""
Write-Host "Captured rows per table:" -ForegroundColor Cyan
foreach ($prop in $counts.PSObject.Properties) {
    if ($prop.Value -gt 0) {
        Write-Host ("    {0,-28} {1,7}" -f $prop.Name, $prop.Value)
    }
}
$empty = @($counts.PSObject.Properties | Where-Object { $_.Value -eq 0 }).Count
Write-Host "    ($empty further tables are empty)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "This snapshot contains real financial data and is deliberately git-ignored." -ForegroundColor Yellow
Write-Host "Restore it with:  ./scripts/restore-my-data.ps1 -Name $Name"
