Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:AgentBranchPrefix = "agent/"
$script:DefaultBaseBranch = "main"
$script:TaskStateFileName = "codex-task.json"

function Assert-CommandExists {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-ExternalText {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$ArgumentList = @()
    )

    $output = & $FilePath @ArgumentList 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | ForEach-Object { $_.ToString() }) -join "`n"

    if ($exitCode -ne 0) {
        throw "Command failed ($exitCode): $FilePath $($ArgumentList -join ' ')`n$text"
    }

    return $text.Trim()
}

function Test-ExternalSuccess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$ArgumentList = @()
    )
    & $FilePath @ArgumentList *> $null
    return ($LASTEXITCODE -eq 0)
}

function Invoke-Git {
    param([Parameter()][string[]]$Arguments = @())
    return Invoke-ExternalText -FilePath "git" -ArgumentList $Arguments
}

function Invoke-Gh {
    param([Parameter()][string[]]$Arguments = @())
    return Invoke-ExternalText -FilePath "gh" -ArgumentList $Arguments
}

function Get-RepoRoot {
    Assert-CommandExists -Name "git"
    if (-not (Test-ExternalSuccess -FilePath "git" -ArgumentList @("rev-parse", "--is-inside-work-tree"))) {
        throw "Current directory is not inside a Git work tree."
    }
    return [System.IO.Path]::GetFullPath((Invoke-Git @("rev-parse", "--show-toplevel")))
}

function Set-RepoRoot {
    $root = Get-RepoRoot
    Set-Location -LiteralPath $root
    return $root
}

function Get-CurrentBranch {
    $branch = Invoke-Git @("branch", "--show-current")
    if ([string]::IsNullOrWhiteSpace($branch)) {
        throw "Detached HEAD is not allowed for guarded agent Git operations."
    }
    return $branch.Trim()
}

function Assert-AgentBranch {
    param([Parameter(Mandatory = $true)][string]$Branch)
    if (-not $Branch.StartsWith($script:AgentBranchPrefix, [System.StringComparison]::Ordinal)) {
        throw "Operation refused: '$Branch' is not an agent/* task branch."
    }
    if ($Branch -eq $script:DefaultBaseBranch) {
        throw "Operation refused on protected base branch '$($script:DefaultBaseBranch)'."
    }
}

function Assert-ValidAgentBranchName {
    param([Parameter(Mandatory = $true)][string]$Branch)

    Assert-AgentBranch -Branch $Branch

    if ($Branch.Length -gt 100 -or $Branch -notmatch '^agent/[a-z0-9][a-z0-9._/-]*$') {
        throw "Invalid agent branch name '$Branch'."
    }
    if ($Branch.Contains("..") -or $Branch.Contains("//") -or $Branch.EndsWith("/") -or $Branch.EndsWith(".")) {
        throw "Invalid agent branch name '$Branch'."
    }
    if (-not (Test-ExternalSuccess -FilePath "git" -ArgumentList @("check-ref-format", "--branch", $Branch))) {
        throw "Git rejected branch name '$Branch'."
    }
}

function New-AgentBranchName {
    param([Parameter(Mandatory = $true)][string]$TaskName)

    $slug = $TaskName.ToLowerInvariant()
    $slug = [regex]::Replace($slug, '[^a-z0-9]+', '-')
    $slug = $slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($slug)) { $slug = "task" }
    if ($slug.Length -gt 40) { $slug = $slug.Substring(0, 40).TrimEnd('-') }

    return "$($script:AgentBranchPrefix)$slug-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
}

function Assert-CleanWorkingTree {
    $status = Invoke-Git @("status", "--porcelain=v1", "--untracked-files=all")
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Working tree is not clean. Autonomous startup/publish refuses to touch existing changes.`n$status"
    }
}

function Assert-OriginExists {
    if (-not (Test-ExternalSuccess -FilePath "git" -ArgumentList @("remote", "get-url", "origin"))) {
        throw "Remote 'origin' is not configured."
    }
}

function Assert-GhAuthenticated {
    Assert-CommandExists -Name "gh"
    & gh auth status *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI is not authenticated. Run 'gh auth login' manually once."
    }
}

function Get-TaskStatePath {
    $gitPath = Invoke-Git @("rev-parse", "--git-path", $script:TaskStateFileName)
    if ([System.IO.Path]::IsPathRooted($gitPath)) {
        return [System.IO.Path]::GetFullPath($gitPath)
    }
    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $gitPath))
}

function Read-TaskStateRaw {
    $path = Get-TaskStatePath
    if (-not (Test-Path -LiteralPath $path)) {
        throw "No guarded task state. Start with scripts/agent/start-task.ps1."
    }
    return Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
}

function Write-TaskStateObject {
    param([Parameter(Mandatory = $true)]$State)
    $path = Get-TaskStatePath
    $parent = Split-Path -Parent $path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $State | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $path -Encoding UTF8
}

function Save-TaskState {
    param(
        [Parameter(Mandatory = $true)][string]$RepoRoot,
        [Parameter(Mandatory = $true)][string]$Branch,
        [Parameter(Mandatory = $true)][string]$Base,
        [Parameter(Mandatory = $true)][string]$StartSha,
        [Parameter(Mandatory = $true)][string]$TaskName
    )

    $state = [ordered]@{
        version       = 2
        repoRoot      = $RepoRoot
        branch        = $Branch
        base          = $Base
        startSha      = $StartSha
        taskName      = $TaskName
        createdAt     = (Get-Date).ToUniversalTime().ToString("o")
        prNumber      = $null
        prUrl         = $null
        mergeReadySha = $null
        mergeReadyAt  = $null
    }

    Write-TaskStateObject -State $state
}

function Load-TaskState {
    $state = Read-TaskStateRaw
    $repoRoot = Get-RepoRoot

    if (-not [string]::Equals(
        [System.IO.Path]::GetFullPath([string]$state.repoRoot),
        [System.IO.Path]::GetFullPath($repoRoot),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Task state belongs to a different repository."
    }

    $branch = Get-CurrentBranch
    if ($branch -ne [string]$state.branch) {
        throw "Current branch '$branch' does not match guarded task '$($state.branch)'."
    }

    Assert-AgentBranch -Branch $branch
    return $state
}

function Set-TaskStateFields {
    param([Parameter(Mandatory = $true)][hashtable]$Fields)
    $state = Load-TaskState
    foreach ($key in $Fields.Keys) {
        if ($state.PSObject.Properties.Name -contains $key) {
            $state.$key = $Fields[$key]
        }
        else {
            $state | Add-Member -NotePropertyName $key -NotePropertyValue $Fields[$key]
        }
    }
    Write-TaskStateObject -State $state
    return $state
}

function Remove-TaskState {
    $path = Get-TaskStatePath
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}

function Assert-ConventionalCommitMessage {
    param([Parameter(Mandatory = $true)][string]$Message)
    $pattern = '^(feat|fix|refactor|test|docs|perf|build|ci|chore)(\([a-z0-9._/-]+\))?!?: .+'
    if ($Message -notmatch $pattern) {
        throw "Commit message must follow Conventional Commits."
    }
    if ($Message.Length -gt 200) {
        throw "Commit subject is too long."
    }
}

function Assert-NoSensitiveStagedPaths {
    $namesText = Invoke-Git @("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    if ([string]::IsNullOrWhiteSpace($namesText)) { return }

    $blocked = New-Object System.Collections.Generic.List[string]

    foreach ($raw in ($namesText -split "`r?`n")) {
        $path = $raw.Trim()
        if ([string]::IsNullOrWhiteSpace($path)) { continue }

        $n = $path.Replace("\", "/").ToLowerInvariant()
        $isEnv = $n -match '(^|/)\.env($|\.)'
        $safeEnv = $n -match '\.env\.(example|sample|template)$'

        $isBlocked =
            ($isEnv -and -not $safeEnv) -or
            ($n -match '\.(pem|key|p12|pfx)$') -or
            ($n -match '(^|/)(id_rsa|id_ed25519)(\.pub)?$') -or
            ($n -match '(^|/)(credentials|service[-_]?account)[^/]*\.json$') -or
            ($n -match '(^|/)(\.npmrc|\.pypirc|\.netrc)$')

        if ($isBlocked) { $blocked.Add($path) }
    }

    if ($blocked.Count -gt 0) {
        Invoke-Git @("restore", "--staged", "--", ".") | Out-Null
        throw "Commit refused: likely-sensitive paths staged:`n- $($blocked -join "`n- ")"
    }
}

function Get-PrObject {
    param([Parameter(Mandatory = $true)][int]$PrNumber)

    Assert-GhAuthenticated
    $json = Invoke-Gh @(
        "pr", "view", "$PrNumber",
        "--json",
        "number,title,url,state,isDraft,baseRefName,headRefName,headRefOid,mergeable,mergeStateStatus,reviewDecision"
    )
    return $json | ConvertFrom-Json
}

function Get-PrChecks {
    param([Parameter(Mandatory = $true)][int]$PrNumber)

    # `gh pr checks` uses non-zero exit codes to communicate check state
    # (for example 8 while checks are pending). That is expected state, not a
    # command-execution failure, so do not route this call through Invoke-Gh.
    $output = & gh pr checks "$PrNumber" --json "bucket,name,state,workflow,link" 2>&1
    $exitCode = $LASTEXITCODE
    $json = ($output | ForEach-Object { $_.ToString() }) -join "`n"

    # 0 = successful command / checks currently passing
    # 1 = one or more checks failed
    # 8 = one or more checks pending
    if ($exitCode -notin @(0, 1, 8)) {
        throw "gh pr checks failed unexpectedly ($exitCode):`n$json"
    }

    if ([string]::IsNullOrWhiteSpace($json)) {
        return @()
    }

    return @($json | ConvertFrom-Json)
}

function Assert-PrMatchesTask {
    param(
        [Parameter(Mandatory = $true)]$Pr,
        [Parameter(Mandatory = $true)]$State
    )

    if ([string]$Pr.baseRefName -ne [string]$State.base) {
        throw "PR base '$($Pr.baseRefName)' != recorded base '$($State.base)'."
    }
    if ([string]$Pr.headRefName -ne [string]$State.branch) {
        throw "PR head '$($Pr.headRefName)' != recorded branch '$($State.branch)'."
    }
}

function Write-GuardedResult {
    param([Parameter(Mandatory = $true)][hashtable]$Data)

    $result = [ordered]@{ status = "ok" }
    foreach ($key in $Data.Keys) { $result[$key] = $Data[$key] }
    $result | ConvertTo-Json -Depth 10
}
