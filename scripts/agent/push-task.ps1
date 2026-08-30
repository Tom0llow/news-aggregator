[CmdletBinding()]
param()

. (Join-Path $PSScriptRoot "_common.ps1")

Set-RepoRoot | Out-Null
$state = Load-TaskState
Assert-OriginExists
Assert-CleanWorkingTree

$branch = [string]$state.branch
$ahead = [int](Invoke-Git @("rev-list", "--count", "$($state.startSha)..HEAD"))
if ($ahead -lt 1) {
    throw "Task branch has no commits beyond its starting SHA."
}

Invoke-Git @("push", "--set-upstream", "origin", "HEAD:refs/heads/$branch") | Out-Null

$localSha = Invoke-Git @("rev-parse", "HEAD")
$remoteText = Invoke-Git @("ls-remote", "--heads", "origin", "refs/heads/$branch")
if ([string]::IsNullOrWhiteSpace($remoteText)) {
    throw "Remote task branch was not found after push."
}

$remoteSha = ($remoteText -split "\s+")[0]
if ($remoteSha -ne $localSha) {
    throw "Remote SHA '$remoteSha' != local HEAD '$localSha'."
}

Write-GuardedResult @{
    operation = "push-task"
    branch    = $branch
    commit    = $localSha
    remote    = "origin"
}
