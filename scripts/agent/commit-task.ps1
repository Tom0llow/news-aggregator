[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Message
)

. (Join-Path $PSScriptRoot "_common.ps1")

Set-RepoRoot | Out-Null
$state = Load-TaskState
Assert-ConventionalCommitMessage -Message $Message

$status = Invoke-Git @("status", "--porcelain=v1", "--untracked-files=all")
if ([string]::IsNullOrWhiteSpace($status)) {
    throw "Nothing to commit."
}

Invoke-Git @("add", "-A", "--", ".") | Out-Null

$staged = Invoke-Git @("diff", "--cached", "--name-only")
if ([string]::IsNullOrWhiteSpace($staged)) {
    throw "No staged changes."
}

Assert-NoSensitiveStagedPaths
Invoke-Git @("diff", "--cached", "--check") | Out-Null
Invoke-Git @("commit", "-m", $Message) | Out-Null

$sha = Invoke-Git @("rev-parse", "HEAD")

# Any new commit invalidates a prior merge-ready result.
Set-TaskStateFields @{
    mergeReadySha = $null
    mergeReadyAt  = $null
} | Out-Null

Write-GuardedResult @{
    operation = "commit-task"
    branch    = [string]$state.branch
    commit    = $sha
    message   = $Message
}
