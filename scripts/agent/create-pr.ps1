[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Title,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Body,
    [Parameter()][switch]$Draft
)

. (Join-Path $PSScriptRoot "_common.ps1")

Set-RepoRoot | Out-Null
$state = Load-TaskState
Assert-OriginExists
Assert-GhAuthenticated
Assert-CleanWorkingTree

$branch = [string]$state.branch
$base = [string]$state.base
$localSha = Invoke-Git @("rev-parse", "HEAD")

$remoteText = Invoke-Git @("ls-remote", "--heads", "origin", "refs/heads/$branch")
if ([string]::IsNullOrWhiteSpace($remoteText)) {
    throw "Remote branch missing. Run push-task.ps1 first."
}

$remoteSha = ($remoteText -split "\s+")[0]
if ($remoteSha -ne $localSha) {
    throw "Remote task branch is not at local HEAD."
}

$existingJson = Invoke-Gh @(
    "pr", "list",
    "--head", $branch,
    "--state", "open",
    "--json", "number,url,title,state,baseRefName,headRefName,isDraft"
)
$existing = @($existingJson | ConvertFrom-Json)

if ($existing.Count -gt 0) {
    $pr = $existing[0]
    if ([string]$pr.baseRefName -ne $base) {
        throw "Existing PR targets wrong base '$($pr.baseRefName)'."
    }

    Set-TaskStateFields @{
        prNumber = [int]$pr.number
        prUrl    = [string]$pr.url
    } | Out-Null

    Write-GuardedResult @{
        operation = "create-pr"
        created   = $false
        number    = [int]$pr.number
        url       = [string]$pr.url
        title     = [string]$pr.title
        base      = [string]$pr.baseRefName
        head      = [string]$pr.headRefName
        draft     = [bool]$pr.isDraft
        headSha   = $localSha
    }
    exit 0
}

$args = @("pr","create","--base",$base,"--head",$branch,"--title",$Title,"--body",$Body)
if ($Draft) { $args += "--draft" }

Invoke-Gh $args | Out-Null

$prJson = Invoke-Gh @(
    "pr","view",$branch,
    "--json","number,title,url,state,baseRefName,headRefName,headRefOid,isDraft"
)
$pr = $prJson | ConvertFrom-Json

if ([string]$pr.baseRefName -ne $base -or [string]$pr.headRefName -ne $branch) {
    throw "Created PR does not match guarded base/head."
}
if ([string]$pr.headRefOid -ne $localSha) {
    throw "Created PR HEAD does not match local HEAD."
}

Set-TaskStateFields @{
    prNumber = [int]$pr.number
    prUrl    = [string]$pr.url
} | Out-Null

Write-GuardedResult @{
    operation = "create-pr"
    created   = $true
    number    = [int]$pr.number
    url       = [string]$pr.url
    title     = [string]$pr.title
    base      = [string]$pr.baseRefName
    head      = [string]$pr.headRefName
    draft     = [bool]$pr.isDraft
    headSha   = [string]$pr.headRefOid
}
