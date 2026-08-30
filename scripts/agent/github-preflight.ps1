[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (& git rev-parse --show-toplevel 2>$null)

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRoot)) {
    throw "Current directory is not inside a Git repository."
}

Set-Location -LiteralPath $repoRoot

$origin = (& git remote get-url origin 2>$null)

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($origin)) {
    throw "Remote 'origin' is not configured."
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) was not found in PATH."
}

# Do NOT use `gh auth status` here.
# The Codex sandbox may incorrectly report a keyring-backed token as invalid.
$user = & gh api user --jq .login 2>&1

if ($LASTEXITCODE -ne 0) {
    $detail = ($user | ForEach-Object { $_.ToString() }) -join "`n"

    throw @"
GitHub API authentication failed from the guarded preflight.

Do not immediately run 'gh auth refresh' only because a sandboxed command
reported 'The token in keyring is invalid'.

Actual error:
$detail
"@
}

$user = ($user | Out-String).Trim()

if ([string]::IsNullOrWhiteSpace($user)) {
    throw "GitHub API succeeded but no login was returned."
}

# Verify Git access to origin/main.
$remoteMain = & git ls-remote --heads origin refs/heads/main 2>&1

if ($LASTEXITCODE -ne 0) {
    $detail = ($remoteMain | ForEach-Object { $_.ToString() }) -join "`n"
    throw "Git remote access failed for origin:`n$detail"
}

# Verify branch protection using the existing script.
$verifyScript = Join-Path $repoRoot "scripts/github/verify-main-protection.ps1"

if (-not (Test-Path -LiteralPath $verifyScript)) {
    throw "Missing branch-protection verifier: $verifyScript"
}

$verifyOutput = & pwsh -NoProfile -File $verifyScript 2>&1

if ($LASTEXITCODE -ne 0) {
    $detail = ($verifyOutput | ForEach-Object { $_.ToString() }) -join "`n"
    throw "GitHub main protection verification failed:`n$detail"
}

$result = [ordered]@{
    status                   = "ok"
    operation                = "github-preflight"
    authenticatedUser        = $user
    origin                   = $origin.Trim()
    originMainFound          = (-not [string]::IsNullOrWhiteSpace(
        ($remoteMain | Out-String).Trim()
    ))
    branchProtectionVerified = $true
}

$result | ConvertTo-Json -Depth 5