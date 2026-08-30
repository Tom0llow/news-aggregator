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
$raw = & gh api `
    -H "Accept: application/vnd.github+json" `
    -H "X-GitHub-Api-Version: 2026-03-10" `
    "repos/$repo/branches/$Branch/protection"

if ($LASTEXITCODE -ne 0) {
    throw "Could not read branch protection."
}

$p = $raw | ConvertFrom-Json

function Get-OptionalPropertyValue {
    param(
        [Parameter(Mandatory = $true)]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) {
        return $null
    }

    return $property.Value
}

$requiredStatusChecks = Get-OptionalPropertyValue -Object $p -Name "required_status_checks"
$contexts = @()
$strictStatusChecks = $false

if ($null -ne $requiredStatusChecks) {
    $contextsProperty = $requiredStatusChecks.PSObject.Properties["contexts"]
    if ($null -ne $contextsProperty -and $null -ne $contextsProperty.Value) {
        $contexts = @($contextsProperty.Value)
    }

    $strictProperty = $requiredStatusChecks.PSObject.Properties["strict"]
    if ($null -ne $strictProperty) {
        $strictStatusChecks = [bool]$strictProperty.Value
    }
}

$requiredPullRequestReviews = Get-OptionalPropertyValue -Object $p -Name "required_pull_request_reviews"

# GitHub omits `required_pull_request_reviews` entirely when no PR review
# requirement is configured. In this project that is the expected state:
# the human gate is explicit merge approval, not a separate GitHub review click.
$humanReviewRequired = ($null -ne $requiredPullRequestReviews)

$missing = @($RequiredChecks | Where-Object { $_ -notin $contexts })

$result = [ordered]@{
    repository                  = $repo
    branch                      = $Branch
    requiredChecksConfigured    = ($missing.Count -eq 0)
    missingChecks               = $missing
    strictStatusChecks          = $strictStatusChecks
    enforceAdmins               = [bool]$p.enforce_admins.enabled
    humanReviewRequired         = $humanReviewRequired
    linearHistory               = [bool]$p.required_linear_history.enabled
    forcePushAllowed            = [bool]$p.allow_force_pushes.enabled
    deletionAllowed             = [bool]$p.allow_deletions.enabled
    conversationResolution      = [bool]$p.required_conversation_resolution.enabled
}

$result | ConvertTo-Json -Depth 10

if (
    -not $result.requiredChecksConfigured -or
    -not $result.strictStatusChecks -or
    -not $result.enforceAdmins -or
    $result.humanReviewRequired -or
    -not $result.linearHistory -or
    $result.forcePushAllowed -or
    $result.deletionAllowed -or
    -not $result.conversationResolution
) {
    exit 2
}

exit 0
