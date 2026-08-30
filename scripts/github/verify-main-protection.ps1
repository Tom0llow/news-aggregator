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
    throw "GitHub API authentication failed.`n$detail"
}

$origin = (& git remote get-url origin 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($origin)) {
    throw "Remote 'origin' is not configured."
}

$repoJson = (& gh repo view --json nameWithOwner 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoJson)) {
    throw "GitHub CLI could not resolve the repository from origin '$origin'."
}
$repo = [string](($repoJson | ConvertFrom-Json).nameWithOwner)
if ([string]::IsNullOrWhiteSpace($repo)) {
    throw "Could not determine GitHub repository owner/name."
}

$repoRaw = & gh api `
    -H "Accept: application/vnd.github+json" `
    -H "X-GitHub-Api-Version: 2026-03-10" `
    "repos/$repo"
if ($LASTEXITCODE -ne 0) {
    throw "Could not read repository settings."
}
$r = $repoRaw | ConvertFrom-Json

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
    if ($null -eq $property) { return $null }
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

$prRule = Get-OptionalPropertyValue -Object $p -Name "required_pull_request_reviews"
$pullRequestRequired = ($null -ne $prRule)
$requiredApprovalCount = -1
$codeOwnerReviewRequired = $false
$lastPushApprovalRequired = $false

if ($pullRequestRequired) {
    $approvalProp = $prRule.PSObject.Properties["required_approving_review_count"]
    if ($null -ne $approvalProp) {
        $requiredApprovalCount = [int]$approvalProp.Value
    }

    $codeOwnerProp = $prRule.PSObject.Properties["require_code_owner_reviews"]
    if ($null -ne $codeOwnerProp) {
        $codeOwnerReviewRequired = [bool]$codeOwnerProp.Value
    }

    $lastPushProp = $prRule.PSObject.Properties["require_last_push_approval"]
    if ($null -ne $lastPushProp) {
        $lastPushApprovalRequired = [bool]$lastPushProp.Value
    }
}

$missing = @($RequiredChecks | Where-Object { $_ -notin $contexts })

$result = [ordered]@{
    repository                  = $repo
    branch                      = $Branch
    requiredChecksConfigured    = ($missing.Count -eq 0)
    missingChecks               = $missing
    strictStatusChecks          = $strictStatusChecks
    enforceAdmins               = [bool]$p.enforce_admins.enabled
    pullRequestRequired         = $pullRequestRequired
    requiredApprovalCount       = $requiredApprovalCount
    codeOwnerReviewRequired     = $codeOwnerReviewRequired
    lastPushApprovalRequired    = $lastPushApprovalRequired
    linearHistory               = [bool]$p.required_linear_history.enabled
    forcePushAllowed            = [bool]$p.allow_force_pushes.enabled
    deletionAllowed             = [bool]$p.allow_deletions.enabled
    conversationResolution      = [bool]$p.required_conversation_resolution.enabled
    squashMergeAllowed          = [bool]$r.allow_squash_merge
    mergeCommitAllowed          = [bool]$r.allow_merge_commit
    rebaseMergeAllowed          = [bool]$r.allow_rebase_merge
    deleteBranchOnMerge         = [bool]$r.delete_branch_on_merge
}

$result | ConvertTo-Json -Depth 10

if (
    -not $result.requiredChecksConfigured -or
    -not $result.strictStatusChecks -or
    -not $result.enforceAdmins -or
    -not $result.pullRequestRequired -or
    $result.requiredApprovalCount -ne 0 -or
    $result.codeOwnerReviewRequired -or
    $result.lastPushApprovalRequired -or
    -not $result.linearHistory -or
    $result.forcePushAllowed -or
    $result.deletionAllowed -or
    -not $result.conversationResolution -or
    -not $result.squashMergeAllowed -or
    $result.mergeCommitAllowed -or
    $result.rebaseMergeAllowed -or
    -not $result.deleteBranchOnMerge
) {
    exit 2
}

exit 0
