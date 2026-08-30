[CmdletBinding()]
param(
    [Parameter()][string]$Branch = "main",
    [Parameter()][string]$Workflow = "ci.yml"
)

. (Join-Path $PSScriptRoot "_common.ps1")

$repoRoot = Set-RepoRoot
Assert-OriginExists

$user = Get-GhLogin

$origin = Invoke-Git @("remote", "get-url", "origin")
$remoteMainText = Invoke-Git @("ls-remote", "--heads", "origin", "refs/heads/$Branch")
if ([string]::IsNullOrWhiteSpace($remoteMainText)) {
    throw "Remote branch 'origin/$Branch' was not found."
}
$remoteMainSha = ($remoteMainText -split "\s+")[0]

# Verify branch/repository policy in a separate process.
$verifyScript = Join-Path $repoRoot "scripts/github/verify-main-protection.ps1"
if (-not (Test-Path -LiteralPath $verifyScript)) {
    throw "Missing branch-protection verifier: $verifyScript"
}

$verifyOutput = & pwsh -NoProfile -File $verifyScript -Branch $Branch 2>&1
$verifyExit = $LASTEXITCODE
if ($verifyExit -ne 0) {
    $detail = ($verifyOutput | ForEach-Object { $_.ToString() }) -join "`n"
    throw "GitHub repository/main policy verification failed:`n$detail"
}

# Baseline main must be green before starting an unrelated autonomous task.
$runJson = Invoke-Gh @(
    "run", "list",
    "--workflow", $Workflow,
    "--branch", $Branch,
    "--limit", "10",
    "--json", "databaseId,status,conclusion,headSha,url,name"
)
$runs = @($runJson | ConvertFrom-Json)
$run = @($runs | Where-Object { [string]$_.headSha -eq $remoteMainSha } | Select-Object -First 1)

if ($run.Count -eq 0) {
    throw "No '$Workflow' workflow run was found for current origin/$Branch HEAD $remoteMainSha."
}

$currentRun = $run[0]
if ([string]$currentRun.status -ne "completed" -or [string]$currentRun.conclusion -ne "success") {
    throw @"
Baseline CI for origin/$Branch is not green.

HEAD: $remoteMainSha
status: $($currentRun.status)
conclusion: $($currentRun.conclusion)
run: $($currentRun.url)

Fix the baseline before starting an unrelated autonomous task.
"@
}

Write-GuardedResult @{
    operation                = "github-preflight"
    authenticatedUser        = $user
    origin                   = $origin.Trim()
    baseBranch               = $Branch
    baseSha                  = $remoteMainSha
    branchProtectionVerified = $true
    baselineCi               = "success"
    baselineCiUrl            = [string]$currentRun.url
}
