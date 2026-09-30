<#
.SYNOPSIS
    One-off: creates Waymark's Android signing key and stores it as GitHub secrets, so every
    release APK is signed with the same key and Settings -> Updates can upgrade the phone app.

.DESCRIPTION
    Android only installs an update signed with the same key as the installed app. Without the
    ANDROID_KEYSTORE_* secrets, release.yml signs with the build machine's throwaway debug key,
    which is different every release. Run this once, as the publisher; people who just use the
    app never need it.

    What it does:
      1. Creates the keystore with keytool (outside the repo: it must never go into git), or
         reuses the one already there.
      2. Asks you for its password. It's passed to keytool and gh through an environment
         variable and a temp file that is deleted straight away. It is never printed, logged or
         put on a command line.
      3. Sets ANDROID_KEYSTORE_B64, ANDROID_KEYSTORE_PASSWORD, ANDROID_KEY_ALIAS and
         ANDROID_KEY_PASSWORD on the GitHub repo with `gh secret set`.
      4. Optionally sets RELEASES_TOKEN too (the token release.yml uses to publish to the public
         waymark-releases repo), if you paste one in.

    BACK UP THE KEYSTORE AND ITS PASSWORD (a password manager is ideal). If either is lost, no
    installed phone can take an update again: everyone would have to uninstall, reinstall and
    re-pair. Never create a second key once releases have gone out with this one.

.PARAMETER KeystorePath
    Where the keystore lives. Defaults to Documents\Waymark signing\waymark-release.keystore.

.PARAMETER Repo
    The GitHub repo to set the secrets on. Defaults to this checkout's repo.

.EXAMPLE
    ./scripts/setup-android-signing.ps1
#>
[CmdletBinding()]
param(
    [string]$KeystorePath = (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Waymark signing\waymark-release.keystore"),
    [string]$Repo
)

# Not "Stop": Windows PowerShell turns anything a native tool (gh, keytool) writes to stderr into
# a terminating error, and keytool reports normal progress there. Exit codes are checked instead.
$ErrorActionPreference = "Continue"
$Alias = "waymark"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Find-Keytool {
    $onPath = Get-Command keytool -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $candidates = @()
    if ($env:JAVA_HOME) { $candidates += Join-Path $env:JAVA_HOME "bin\keytool.exe" }
    $candidates += "$env:ProgramFiles\Android\Android Studio\jbr\bin\keytool.exe"
    foreach ($pattern in @("$env:ProgramFiles\Microsoft\jdk-*\bin\keytool.exe",
                           "$env:ProgramFiles\Eclipse Adoptium\*\bin\keytool.exe",
                           "$env:ProgramFiles\Java\*\bin\keytool.exe")) {
        $candidates += Get-ChildItem $pattern -ErrorAction SilentlyContinue | ForEach-Object FullName
    }
    return $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

function Read-Password([string]$Prompt) {
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

# Feeds the value to `gh secret set` on stdin from a temp file, so it never appears on a
# command line; the file is deleted as soon as gh has read it.
function Set-Secret([string]$Name, [string]$Value) {
    $tmp = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($tmp, $Value)
        $p = Start-Process gh -ArgumentList @("secret", "set", $Name, "--repo", $Repo) `
            -RedirectStandardInput $tmp -NoNewWindow -Wait -PassThru
        if ($p.ExitCode -ne 0) { throw "gh couldn't set $Name (exit $($p.ExitCode))." }
        Write-Host "    set $Name"
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

# --- Preflight ------------------------------------------------------------------------------
$keytool = Find-Keytool
if (-not $keytool) {
    throw "keytool wasn't found. It comes with Java: install it with 'winget install Microsoft.OpenJDK.17', open a new terminal and run this again."
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "The GitHub CLI (gh) isn't installed." }
gh auth status *> $null
if ($LASTEXITCODE -ne 0) { throw "gh isn't signed in. Run 'gh auth login' (choose GitHub.com, HTTPS, and log in with a web browser), then run this again." }
if (-not $Repo) {
    Push-Location $repoRoot
    try { $Repo = gh repo view --json nameWithOwner -q .nameWithOwner 2>$null } finally { Pop-Location }
    if (-not $Repo) { throw "Couldn't work out the GitHub repo. Run again with -Repo parnelljamie/networth-tracker." }
}
$fullRepoRoot = [IO.Path]::GetFullPath($repoRoot).TrimEnd('\') + '\'
if ([IO.Path]::GetFullPath($KeystorePath).StartsWith($fullRepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Keep the keystore outside the repo ($repoRoot) so it can never be committed."
}

Write-Host "Repo:     $Repo"
Write-Host "Keystore: $KeystorePath"
Write-Host "keytool:  $keytool"
Write-Host ""

# --- 1. Keystore ----------------------------------------------------------------------------
$env:WAYMARK_KEYSTORE_PASS = $null
try {
    if (Test-Path $KeystorePath) {
        Write-Host "==> Using the existing keystore (it is never replaced; a new key would break phone updates)."
        $password = Read-Password "Keystore password"
        $env:WAYMARK_KEYSTORE_PASS = $password
        & $keytool -list -keystore $KeystorePath -alias $Alias '-storepass:env' WAYMARK_KEYSTORE_PASS *> $null
        if ($LASTEXITCODE -ne 0) { throw "That password doesn't open $KeystorePath (or it has no '$Alias' key)." }
    } else {
        Write-Host "==> Creating a new signing key."
        $password = Read-Password "Choose a keystore password (at least 8 characters)"
        if ($password.Length -lt 8) { throw "Use at least 8 characters." }
        if ($password -ne (Read-Password "Type it again")) { throw "The passwords didn't match." }
        $env:WAYMARK_KEYSTORE_PASS = $password
        New-Item -ItemType Directory -Force (Split-Path -Parent $KeystorePath) -ErrorAction Stop | Out-Null
        # PKCS12 uses one password for the store and the key. ~27 years' validity.
        & $keytool -genkeypair -keystore $KeystorePath -storetype PKCS12 -alias $Alias `
            -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=Waymark" `
            '-storepass:env' WAYMARK_KEYSTORE_PASS '-keypass:env' WAYMARK_KEYSTORE_PASS
        if ($LASTEXITCODE -ne 0) { throw "keytool couldn't create the keystore." }
        Write-Host "    created $KeystorePath"
    }

    # --- 2. Secrets ---------------------------------------------------------------------------
    Write-Host "==> Setting the Android signing secrets on $Repo"
    Set-Secret "ANDROID_KEYSTORE_B64" ([Convert]::ToBase64String([IO.File]::ReadAllBytes($KeystorePath)))
    Set-Secret "ANDROID_KEYSTORE_PASSWORD" $password
    Set-Secret "ANDROID_KEY_ALIAS" $Alias
    Set-Secret "ANDROID_KEY_PASSWORD" $password
} finally {
    $env:WAYMARK_KEYSTORE_PASS = $null
    $password = $null
}

# --- 3. Optional: RELEASES_TOKEN ------------------------------------------------------------
Write-Host ""
Write-Host "Optional: the token release.yml uses to publish to the public waymark-releases repo."
Write-Host "Create it at https://github.com/settings/personal-access-tokens/new : fine-grained,"
Write-Host "Repository access 'Only select repositories' = waymark-releases, Permissions: Contents = Read and write."
$token = Read-Password "Paste the token (or just press Enter to skip)"
# The input is hidden, so a bad paste (a stray newline, or a literal Ctrl+V in some consoles)
# goes unnoticed until the release workflow fails. Check its shape before storing it.
while ($token -and ($token.Trim() -notmatch '^(github_pat_|ghp_)[A-Za-z0-9_]+$')) {
    Write-Host "    That doesn't look like a GitHub token (it should start github_pat_). Paste it again; right-click pastes if Ctrl+V doesn't."
    $token = Read-Password "Paste the token (or just press Enter to skip)"
}
if ($token) {
    $token = $token.Trim()
    Set-Secret "RELEASES_TOKEN" $token
    $token = $null
} else {
    Write-Host "    skipped RELEASES_TOKEN"
}

# --- Done -----------------------------------------------------------------------------------
Write-Host ""
Write-Host "Done. Secrets now on ${Repo}:"
gh secret list --repo $Repo
Write-Host ""
Write-Host "NEXT:" -ForegroundColor Yellow
Write-Host "  1. Back up $KeystorePath and its password now (a password manager is ideal)."
Write-Host "     If either is lost, installed phones can never take an update again."
Write-Host "  2. The next release APK is signed with this key. Uninstall the phone app once, install"
Write-Host "     that release, and pair it with the PC again. Updates work in place from then on."
