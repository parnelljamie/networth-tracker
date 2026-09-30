# Phase 7: registers a Windows Task Scheduler task that starts the server hidden (no window)
# at logon, so the daily snapshot, price refresh and backup jobs run even when nobody opens
# the app. Not the Phase 9 installer — this is the dev/pre-installer convenience described in
# docs/01-architecture.md "Runtime > Always-on (recommended, Phase 7)".
#
# Run once, from an ordinary (non-admin) PowerShell prompt:
#   ./scripts/install-autostart.ps1
# Remove it again with:
#   ./scripts/install-autostart.ps1 -Uninstall

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$TaskName = "Waymark (background)"
# What the task was called before the app was renamed from Passbook.
$LegacyTaskName = "Passbook (background)"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (Get-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $LegacyTaskName -Confirm:$false
    Write-Host "Removed the old scheduled task '$LegacyTaskName'."
}

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'."
    } else {
        Write-Host "No scheduled task named '$TaskName' found."
    }
    return
}

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    throw "uv is not on PATH. Install it first (see docs/01-architecture.md) then re-run this script."
}

$desktopScript = Join-Path $repoRoot "scripts\desktop.py"
if (-not (Test-Path $desktopScript)) {
    throw "Could not find $desktopScript"
}

# `uv run` resolves the project from the working directory, so the action's start-in directory
# must be backend/ (where pyproject.toml lives) and the script path must be given relative to it.
$backendDir = Join-Path $repoRoot "backend"
$relativeScript = "..\scripts\desktop.py"

$action = New-ScheduledTaskAction `
    -Execute $uv `
    -Argument "run python `"$relativeScript`" --background" `
    -WorkingDirectory $backendDir

$trigger = New-ScheduledTaskTrigger -AtLogOn

# Hidden: no console window, no taskbar entry. Runs only for the current user, no elevation.
$settings = New-ScheduledTaskSettingsSet `
    -Hidden `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) # unlimited: this is meant to run all day

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Runs Waymark's server in the background (no window) at logon, so daily snapshots, price refreshes and backups happen automatically. Installed by scripts/install-autostart.ps1." `
    -Force | Out-Null

Write-Host "Installed scheduled task '$TaskName' - it will run at your next logon."
Write-Host "To start it immediately without logging off: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "To remove it: ./scripts/install-autostart.ps1 -Uninstall"
