[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter()][string[]]$RequiredChecks = @("Quality", "Test")
)

. (Join-Path $PSScriptRoot "_common.ps1")

Set-RepoRoot | Out-Null
$state = Load-TaskState
Assert-OriginExists
Assert-GhAuthenticated
Assert-CleanWorkingTree

$pr = Get-PrObject -PrNumber $PrNumber
Assert-PrMatchesTask -Pr $pr -State $state

if ([string]$pr.state -ne "OPEN") { throw "PR is not open." }
if ([bool]$pr.isDraft) { throw "PR is still a draft." }
if ([string]$pr.mergeable -ne "MERGEABLE") {
    throw "PR is not mergeable: $($pr.mergeable)."
}
if ([string]$pr.mergeStateStatus -ne "CLEAN") {
    throw "PR merge state is '$($pr.mergeStateStatus)', not CLEAN."
}

$decision = [string]$pr.reviewDecision
if ($decision -eq "CHANGES_REQUESTED" -or $decision -eq "REVIEW_REQUIRED") {
    throw "PR review decision blocks merge: '$decision'."
}

$localSha = Invoke-Git @("rev-parse", "HEAD")
if ($localSha -ne [string]$pr.headRefOid) {
    throw "Local HEAD != PR HEAD. Push/review the actual current HEAD first."
}

$remoteText = Invoke-Git @("ls-remote", "--heads", "origin", "refs/heads/$($state.branch)")
if ([string]::IsNullOrWhiteSpace($remoteText)) {
    throw "Remote task branch is missing."
}
$remoteSha = ($remoteText -split "\s+")[0]
if ($remoteSha -ne $localSha) {
    throw "Remote task branch != local HEAD."
}

$checks = @(Get-PrChecks -PrNumber $PrNumber)
Assert-ChecksReady -Checks $checks -RequiredChecks $RequiredChecks

$now = (Get-Date).ToUniversalTime().ToString("o")
Set-TaskStateFields @{
    prNumber      = $PrNumber
    prUrl         = [string]$pr.url
    mergeReadySha = [string]$pr.headRefOid
    mergeReadyAt  = $now
} | Out-Null

Write-GuardedResult @{
    operation      = "merge-ready"
    ready          = $true
    prNumber       = $PrNumber
    url            = [string]$pr.url
    title          = [string]$pr.title
    headSha        = [string]$pr.headRefOid
    mergeable      = [string]$pr.mergeable
    mergeState     = [string]$pr.mergeStateStatus
    reviewDecision = $decision
    requiredChecks = $RequiredChecks
    checks         = $checks
    mergeReadyAt   = $now
}
