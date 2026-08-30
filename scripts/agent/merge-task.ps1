[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40,64}$')][string]$ExpectedHeadSha
)

. (Join-Path $PSScriptRoot "_common.ps1")

Set-RepoRoot | Out-Null
$state = Load-TaskState
Assert-OriginExists
Assert-GhAuthenticated
Assert-CleanWorkingTree

if ([int]$state.prNumber -ne $PrNumber) {
    throw "PR #$PrNumber is not the recorded task PR #$($state.prNumber)."
}
if ([string]::IsNullOrWhiteSpace([string]$state.mergeReadySha)) {
    throw "No recorded MERGE_READY state. Run merge-ready.ps1 first."
}
if (-not [string]::Equals([string]$state.mergeReadySha, $ExpectedHeadSha, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Expected SHA is not the SHA that was recorded as MERGE_READY."
}

$pr = Get-PrObject -PrNumber $PrNumber
Assert-PrMatchesTask -Pr $pr -State $state

if ([string]$pr.state -ne "OPEN" -or [bool]$pr.isDraft) {
    throw "PR must be open and non-draft."
}
if (-not [string]::Equals([string]$pr.headRefOid, $ExpectedHeadSha, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "PR HEAD changed after human approval. Re-review and obtain approval again."
}
if ([string]$pr.mergeable -ne "MERGEABLE" -or [string]$pr.mergeStateStatus -ne "CLEAN") {
    throw "PR is no longer cleanly mergeable."
}

$decision = [string]$pr.reviewDecision
if ($decision -eq "CHANGES_REQUESTED" -or $decision -eq "REVIEW_REQUIRED") {
    throw "Review decision now blocks merge: '$decision'."
}

$checks = Get-PrChecks -PrNumber $PrNumber
if ($checks.Count -eq 0) { throw "No CI checks found." }

$blocking = @($checks | Where-Object {
    $bucket = [string]$_.bucket
    ($bucket -ne "pass") -and ($bucket -ne "skipping")
})
if ($blocking.Count -gt 0) {
    throw "CI/status checks are no longer all passing."
}

# Exact reviewed HEAD + squash merge only.
Invoke-Gh @(
    "pr","merge","$PrNumber",
    "--squash",
    "--delete-branch",
    "--match-head-commit",$ExpectedHeadSha
) | Out-Null

$after = (Invoke-Gh @("pr","view","$PrNumber","--json","number,url,state,mergedAt")) | ConvertFrom-Json
if ([string]$after.state -ne "MERGED") {
    throw "Merge command returned but PR is not reported as MERGED."
}

$cleanup = "not-attempted"
try {
    $taskBranch = [string]$state.branch
    Invoke-Git @("fetch","origin",$script:DefaultBaseBranch) | Out-Null
    Invoke-Git @("switch",$script:DefaultBaseBranch) | Out-Null
    Invoke-Git @("merge","--ff-only","origin/$($script:DefaultBaseBranch)") | Out-Null

    if (Test-ExternalSuccess "git" @("show-ref","--verify","--quiet","refs/heads/$taskBranch")) {
        Invoke-Git @("branch","-d",$taskBranch) | Out-Null
    }
    Remove-TaskState
    $cleanup = "completed"
}
catch {
    # Remote merge already succeeded. Never turn that into a false merge failure.
    $cleanup = "manual-cleanup-required: $($_.Exception.Message)"
}

Write-GuardedResult @{
    operation     = "merge-task"
    number        = [int]$after.number
    url           = [string]$after.url
    state         = [string]$after.state
    mergedAt      = [string]$after.mergedAt
    mergedHeadSha = $ExpectedHeadSha
    method        = "squash"
    localCleanup  = $cleanup
}
