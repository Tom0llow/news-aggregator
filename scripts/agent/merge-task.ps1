[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F]{40,64}$')][string]$ExpectedHeadSha,
    [Parameter()][string[]]$RequiredChecks = @("Quality", "Test")
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
if (-not [string]::Equals(
    [string]$state.mergeReadySha,
    $ExpectedHeadSha,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Expected SHA is not the SHA that was recorded as MERGE_READY."
}

$pr = Get-PrObject -PrNumber $PrNumber
Assert-PrMatchesTask -Pr $pr -State $state

if ([string]$pr.state -ne "OPEN" -or [bool]$pr.isDraft) {
    throw "PR must be open and non-draft."
}
if (-not [string]::Equals(
    [string]$pr.headRefOid,
    $ExpectedHeadSha,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "PR HEAD changed after human approval. Re-review and obtain approval again."
}
if ([string]$pr.mergeable -ne "MERGEABLE" -or [string]$pr.mergeStateStatus -ne "CLEAN") {
    throw "PR is no longer cleanly mergeable."
}

$decision = [string]$pr.reviewDecision
if ($decision -eq "CHANGES_REQUESTED" -or $decision -eq "REVIEW_REQUIRED") {
    throw "Review decision now blocks merge: '$decision'."
}

$checks = @(Get-PrChecks -PrNumber $PrNumber)
Assert-ChecksReady -Checks $checks -RequiredChecks $RequiredChecks

# Exact reviewed HEAD + squash only. Remote branch deletion is handled explicitly
# below so local Git state is not implicitly changed by `gh`.
Invoke-Gh @(
    "pr", "merge", "$PrNumber",
    "--squash",
    "--match-head-commit", $ExpectedHeadSha
) | Out-Null

$after = (Invoke-Gh @("pr", "view", "$PrNumber", "--json", "number,url,state,mergedAt")) | ConvertFrom-Json
if ([string]$after.state -ne "MERGED") {
    throw "Merge command returned but PR is not reported as MERGED."
}

$cleanupMessages = New-Object System.Collections.Generic.List[string]
$taskBranch = [string]$state.branch

try {
    Invoke-Git @("fetch", "--prune", "origin", $script:DefaultBaseBranch) | Out-Null
    Invoke-Git @("switch", $script:DefaultBaseBranch) | Out-Null
    Invoke-Git @("merge", "--ff-only", "origin/$($script:DefaultBaseBranch)") | Out-Null

    $remoteTask = Invoke-Git @("ls-remote", "--heads", "origin", "refs/heads/$taskBranch")
    if (-not [string]::IsNullOrWhiteSpace($remoteTask)) {
        Invoke-Git @("push", "origin", "--delete", $taskBranch) | Out-Null
    }

    if (Test-ExternalSuccess "git" @("show-ref", "--verify", "--quiet", "refs/heads/$taskBranch")) {
        # A squash merge does not mark the feature branch as graph-merged, so -d
        # can refuse. -D is safe here only because the exact remote PR merge was
        # already revalidated and confirmed above.
        Invoke-Git @("branch", "-D", $taskBranch) | Out-Null
    }

    $cleanupMessages.Add("completed")
}
catch {
    $cleanupMessages.Add("manual-cleanup-required: $($_.Exception.Message)")
}

# The remote merge is the terminal state of this task. Do not leave stale task
# identity behind even if local cleanup needs manual attention.
try {
    Remove-TaskState
}
catch {
    $cleanupMessages.Add("task-state-cleanup-failed: $($_.Exception.Message)")
}

Write-GuardedResult @{
    operation     = "merge-task"
    number        = [int]$after.number
    url           = [string]$after.url
    state         = [string]$after.state
    mergedAt      = [string]$after.mergedAt
    mergedHeadSha = $ExpectedHeadSha
    method        = "squash"
    localCleanup  = ($cleanupMessages -join "; ")
}
