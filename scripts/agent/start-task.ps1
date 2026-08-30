[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$TaskName,
    [Parameter()][string]$BranchName,
    [Parameter()][ValidateNotNullOrEmpty()][string]$Base = "main"
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
Assert-OriginExists
Assert-CleanWorkingTree

if ($Base -ne $script:DefaultBaseBranch) {
    throw "Autonomous tasks currently permit only base '$($script:DefaultBaseBranch)'."
}

if ([string]::IsNullOrWhiteSpace($BranchName)) {
    $BranchName = New-AgentBranchName -TaskName $TaskName
}
Assert-ValidAgentBranchName -Branch $BranchName

if (Test-ExternalSuccess "git" @("show-ref", "--verify", "--quiet", "refs/heads/$BranchName")) {
    throw "Local branch '$BranchName' already exists."
}

Invoke-Git @("fetch", "--prune", "origin", $Base) | Out-Null

if (-not (Test-ExternalSuccess "git" @("rev-parse", "--verify", "origin/$Base"))) {
    throw "Remote base 'origin/$Base' was not found."
}

$startSha = Invoke-Git @("rev-parse", "origin/$Base")
$remoteBranch = Invoke-Git @("ls-remote", "--heads", "origin", "refs/heads/$BranchName")
if (-not [string]::IsNullOrWhiteSpace($remoteBranch)) {
    throw "Remote branch '$BranchName' already exists."
}

Invoke-Git @("switch", "--create", $BranchName, "origin/$Base") | Out-Null

Save-TaskState -RepoRoot $repoRoot -Branch $BranchName -Base $Base -StartSha $startSha -TaskName $TaskName

Write-GuardedResult @{
    operation = "start-task"
    taskName  = $TaskName
    branch    = $BranchName
    base      = $Base
    startSha  = $startSha
}
