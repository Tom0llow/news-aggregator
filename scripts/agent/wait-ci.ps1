[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$PrNumber,
    [Parameter()][ValidateRange(1, 7200)][int]$TimeoutSeconds = 1800,
    [Parameter()][ValidateRange(5, 300)][int]$IntervalSeconds = 15
)

. (Join-Path $PSScriptRoot "_common.ps1")

Set-RepoRoot | Out-Null
$state = Load-TaskState
Assert-GhAuthenticated

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$last = @()

while ((Get-Date) -lt $deadline) {
    $pr = Get-PrObject -PrNumber $PrNumber
    Assert-PrMatchesTask -Pr $pr -State $state

    $checks = Get-PrChecks -PrNumber $PrNumber
    $last = $checks

    if ($checks.Count -eq 0) {
        Start-Sleep -Seconds $IntervalSeconds
        continue
    }

    $failed = @($checks | Where-Object {
        ([string]$_.bucket -eq "fail") -or
        ([string]$_.bucket -eq "cancel")
    })

    if ($failed.Count -gt 0) {
        @{
            status   = "failed"
            prNumber = $PrNumber
            headSha  = [string]$pr.headRefOid
            checks   = $checks
        } | ConvertTo-Json -Depth 10
        exit 2
    }

    $pending = @($checks | Where-Object {
        $bucket = [string]$_.bucket
        ($bucket -ne "pass") -and ($bucket -ne "skipping")
    })

    if ($pending.Count -eq 0) {
        @{
            status   = "passed"
            prNumber = $PrNumber
            headSha  = [string]$pr.headRefOid
            checks   = $checks
        } | ConvertTo-Json -Depth 10
        exit 0
    }

    Start-Sleep -Seconds $IntervalSeconds
}

@{
    status   = "timeout"
    prNumber = $PrNumber
    checks   = $last
} | ConvertTo-Json -Depth 10

exit 3
