[CmdletBinding()]
param(
    [Parameter()][string]$Branch = "main",
    [Parameter()][string[]]$RequiredChecks = @("Quality", "Test")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required."
}

& gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Run 'gh auth login' first."
}

$origin = (& git remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($origin)) {
    throw @"
Remote 'origin' is not configured.

Check:
  git remote -v

If the GitHub repository already exists:
  git remote add origin <github-repository-url>

If it does not exist yet, create/publish the repository first, then rerun this script.
"@
}

$repoJson = (& gh repo view --json nameWithOwner 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoJson)) {
    throw "GitHub CLI could not resolve the repository from origin '$origin'. Verify 'gh auth status' and 'git remote -v'."
}

$repoObject = $repoJson | ConvertFrom-Json
if ($null -eq $repoObject -or -not ($repoObject.PSObject.Properties.Name -contains "nameWithOwner")) {
    throw "GitHub CLI returned repository metadata without 'nameWithOwner'. Verify origin points to a GitHub repository."
}

$repo = [string]$repoObject.nameWithOwner
if ([string]::IsNullOrWhiteSpace($repo)) {
    throw "Could not determine GitHub repository owner/name."
}


$body = @{
    required_status_checks = @{
        strict = $true
        contexts = $RequiredChecks
    }
    enforce_admins = $true

    # Deliberately no required human GitHub reviewer.
    # The human gate is the explicit merge approval in the Codex workflow.
    required_pull_request_reviews = $null

    restrictions = $null
    required_linear_history = $true
    allow_force_pushes = $false
    allow_deletions = $false
    block_creations = $false
    required_conversation_resolution = $true
    lock_branch = $false
    allow_fork_syncing = $true
} | ConvertTo-Json -Depth 10

$body | gh api `
    --method PUT `
    -H "Accept: application/vnd.github+json" `
    -H "X-GitHub-Api-Version: 2026-03-10" `
    "repos/$repo/branches/$Branch/protection" `
    --input -

if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure branch protection. Admin/owner permission may be required."
}

Write-Host "Configured protection for ${repo}:$Branch"
Write-Host "Required checks: $($RequiredChecks -join ', ')"
