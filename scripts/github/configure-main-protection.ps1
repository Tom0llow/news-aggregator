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

$user = & gh api user --jq .login 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($user | Out-String).Trim())) {
    $detail = ($user | ForEach-Object { $_.ToString() }) -join "`n"
    throw "GitHub API authentication failed. Run this admin script from an authenticated host terminal.`n$detail"
}

$origin = (& git remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($origin)) {
    throw "Remote 'origin' is not configured."
}

$repoJson = (& gh repo view --json nameWithOwner 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoJson)) {
    throw "GitHub CLI could not resolve the repository from origin '$origin'."
}

$repoObject = $repoJson | ConvertFrom-Json
$repo = [string]$repoObject.nameWithOwner
if ([string]::IsNullOrWhiteSpace($repo)) {
    throw "Could not determine GitHub repository owner/name."
}

# Repository merge policy: autonomous merge is squash-only.
$repoPolicy = @{
    allow_squash_merge = $true
    allow_merge_commit = $false
    allow_rebase_merge = $false
    delete_branch_on_merge = $true
} | ConvertTo-Json -Depth 5

$repoPolicy | gh api `
    --method PATCH `
    -H "Accept: application/vnd.github+json" `
    -H "X-GitHub-Api-Version: 2026-03-10" `
    "repos/$repo" `
    --input - | Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure repository merge policy."
}

# Require PRs, but require zero human GitHub approvals.
# The human boundary is the exact MERGE_READY HEAD approval in Codex.
$body = @{
    required_status_checks = @{
        strict = $true
        contexts = $RequiredChecks
    }
    enforce_admins = $true
    required_pull_request_reviews = @{
        dismiss_stale_reviews = $false
        require_code_owner_reviews = $false
        required_approving_review_count = 0
        require_last_push_approval = $false
    }
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
    --input - | Out-Null

if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure branch protection. Admin/owner permission may be required."
}

Write-Host "Configured repository/branch policy for ${repo}:$Branch"
Write-Host "Required checks: $($RequiredChecks -join ', ')"
Write-Host "PR required: yes; GitHub approvals required: 0; merge method: squash only"
