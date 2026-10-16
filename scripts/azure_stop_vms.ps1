param([ValidateSet('Cost','Force','Daily')][string]$Mode = 'Cost', [object]$WebhookData)
# Never log webhook bodies or access tokens. Automation system identity only.
$ErrorActionPreference = 'Stop'
Disable-AzContextAutosave -Scope Process | Out-Null
Connect-AzAccount -Identity | Out-Null
$ProgressPreference = 'SilentlyContinue'
function Get-CostResponse([string]$Path, [string]$Body) {
    # Invoke-AzRestMethod has no request-Headers parameter. Use the official
    # managed-identity access token with WebRequest for a fixed ClientType.
    $token = (Get-AzAccessToken -ResourceUrl 'https://management.azure.com/').Token
    if ($token -is [System.Security.SecureString]) {
        $plain = (New-Object System.Net.NetworkCredential('', $token)).Password
    } else { $plain = $token }
    try {
        for ($attempt=0; $attempt -le 3; $attempt++) {
            try {
                return Invoke-WebRequest -UseBasicParsing -Uri "https://management.azure.com$Path" -Method POST -Body $Body -ContentType 'application/json' -Headers @{Authorization="Bearer $plain";ClientType='UGRPSimulationCostGuard'}
            } catch {
                $response = $_.Exception.Response
                if ($null -eq $response -or [int]$response.StatusCode -ne 429 -or $attempt -eq 3) { throw }
                $delay = 60
                foreach ($key in $response.Headers.AllKeys) {
                    if ($key -match 'retry-after' -and $response.Headers[$key] -match '^\d+(\.\d+)?$') {
                        $delay = [Math]::Max($delay, [double]$response.Headers[$key])
                    }
                }
                if ($delay -gt 600) { throw }
                Write-Warning "Cost query throttled; retry-after=$delay seconds"
                Start-Sleep -Seconds $delay
            }
        }
    } finally { $plain = $null; $token = $null }
}
$subscriptions = @('88b7ee7f-f2f3-4a0d-a0ce-cf7306943676','c02f839a-2a6b-49d8-9c9a-f3d9f09aa5ea')
$stop = $Mode -in @('Force','Daily') -or [DateTime]::UtcNow -ge [DateTime]'2026-11-18T15:00:00Z'
$total = 0.0
if (-not $stop) {
    try {
        foreach ($sub in $subscriptions) {
            $body = @{type='ActualCost';timeframe='Custom';timePeriod=@{from='2026-10-01T00:00:00Z';to=[DateTime]::UtcNow.ToString('o')};dataset=@{granularity='None';aggregation=@{usd=@{name='CostUSD';function='Sum'}}}} | ConvertTo-Json -Depth 8
            $result = Get-CostResponse "/subscriptions/$sub/providers/Microsoft.CostManagement/query?api-version=2025-03-01" $body
            if ($result.StatusCode -ne 200) { throw 'Cost query failed' }
            $data = ($result.Content | ConvertFrom-Json).properties
            $index = [array]::IndexOf(@($data.columns.name), 'CostUSD')
            if ($index -lt 0 -or $data.nextLink) { throw 'Unrecognized or paginated cost result' }
            foreach ($row in $data.rows) { $total += [double]$row[$index] }
        }
        # $150 early stop provides headroom for delayed cost reporting.
        $stop = $total -ge 150
        Write-Output "CumulativeCostUSD=$total Stop=$stop"
    } catch {
        # A failed cost check cannot leave paid compute running indefinitely.
        $stop = $true
        Write-Output "Cost check error type=$($_.Exception.GetType().Name) code=$($_.FullyQualifiedErrorId)"
        Write-Output 'COST_CHECK_FAILED: fail closed, deallocate both subscriptions'
    }
}
if (-not $stop) { return }
# Managed Run Command is asynchronous; a guest failure never cancels a cost cap.
# All VMs share this ten-minute deadline, including agent/API failures.
$deadline = [DateTime]::UtcNow.AddSeconds(600)
$GuestScript = @'
guard=$(mktemp /tmp/ugrp-grace.XXXXXX.py)
cat > "$guard" <<'UGRP_PY'
__UGRP_SHUTDOWN_SOURCE__
UGRP_PY
chmod 644 "$guard"
/usr/sbin/runuser -u ugrp -- /usr/bin/python3 "$guard" GUARD_ACTION
result=$?
rm -f "$guard"
exit "$result"
'@
$guardAction = if ($Mode -eq 'Daily' -and [DateTime]::UtcNow -lt [DateTime]'2026-11-18T15:00:00Z') { 'daily' } else { 'stop' }
$GuestScript = $GuestScript.Replace('GUARD_ACTION', $guardAction)
function Invoke-GuardRest([string]$Method, [string]$Path, [string]$Body) {
    $left = [Math]::Max(1, [Math]::Min(30, ($deadline - [DateTime]::UtcNow).TotalSeconds))
    $token = (Get-AzAccessToken -ResourceUrl 'https://management.azure.com/').Token
    $plain = if ($token -is [System.Security.SecureString]) { (New-Object System.Net.NetworkCredential('', $token)).Password } else { $token }
    try {
        $params = @{UseBasicParsing=$true;Uri="https://management.azure.com$Path";Method=$Method;TimeoutSec=[int]$left;Headers=@{Authorization="Bearer $plain"}}
        if ($Body) { $params.Body=$Body; $params.ContentType='application/json' }
        return Invoke-WebRequest @params
    } finally { $plain=$null; $token=$null }
}
$failed = @()
$pending = @()
foreach ($sub in $subscriptions) {
    try {
        $path = "/subscriptions/$sub/providers/Microsoft.Compute/virtualMachines?api-version=2024-11-01"
        do {
            $response = Invoke-GuardRest 'GET' $path ''
            if ($response.StatusCode -ne 200) { throw 'VM discovery failed' }
            $data = $response.Content | ConvertFrom-Json
            foreach ($vm in $data.value) {
                try {
                    $view = Invoke-GuardRest 'GET' "$($vm.id)/instanceView?api-version=2024-11-01" ''
                    if (($view.Content | ConvertFrom-Json).statuses.code -contains 'PowerState/deallocated') {
                        Write-Output "Already deallocated $($vm.id)"
                        continue
                    }
                } catch { Write-Output "Instance view unavailable $($vm.id); attempt graceful stop anyway" }
                $command = "$($vm.id)/runCommands/ugrp-grace-$([Guid]::NewGuid().ToString('N'))"
                $entry = @{vm=$vm.id;command=$command;done=$false;dailySkip=$false}
                $pending += $entry
                try {
                    $body = @{location=$vm.location;properties=@{source=@{script=$GuestScript};asyncExecution=$true;timeoutInSeconds=570}} | ConvertTo-Json -Depth 8
                    $result = Invoke-GuardRest 'PUT' "$command`?api-version=2024-11-01" $body
                    Write-Output "GracefulStop $($vm.id) HTTP=$($result.StatusCode)"
                } catch {
                    Write-Output "GracefulStop dispatch failed $($vm.id); persistent originals retained"
                    $entry.done=$true
                    $entry.dailySkip=$guardAction -eq 'daily'
                }
            }
            $path = $data.nextLink -replace '^https://management.azure.com',''
        } while ($path)
    } catch { $failed += $sub }
}
while (@($pending | Where-Object { -not $_.done }).Count -and [DateTime]::UtcNow -lt $deadline) {
    foreach ($entry in $pending) {
        if ($entry.done -or [DateTime]::UtcNow -ge $deadline) { continue }
        try {
            $response = Invoke-GuardRest 'GET' "$($entry.command)?api-version=2024-11-01&`$expand=instanceView" ''
            $view = ($response.Content | ConvertFrom-Json).properties.instanceView
            if ($view.executionState -in @('Succeeded','Failed','TimedOut','Canceled')) {
                $entry.done=$true
                $entry.dailySkip=($guardAction -eq 'daily' -and $view.exitCode -ne 0)
                # No secrets: helper emits only run names, PIDs, archive outcome.
                Write-Output "GracefulResult $($entry.vm) Exit=$($view.exitCode) Output=$($view.output)"
            }
        } catch { Write-Output "GracefulStop poll failed $($entry.vm); retry until deadline" }
    }
    $left = ($deadline - [DateTime]::UtcNow).TotalSeconds
    if ($left -gt 0 -and @($pending | Where-Object { -not $_.done }).Count) { Start-Sleep -Seconds ([Math]::Min(5, $left)) }
}
foreach ($entry in $pending) {
    # Midnight is only a backup: uncertain state or active lease => skip + log.
    if ($guardAction -eq 'daily' -and (-not $entry.done -or $entry.dailySkip)) {
        Write-Output "DAILY_SKIPPED $($entry.vm): lease/unarchived work or guest verification unavailable"
        continue
    }
    if (-not $entry.done) { Write-Output "GracefulStop timeout $($entry.vm); retry archive on next boot" }
    try {
        $result = Invoke-AzRestMethod -Method POST -Path "$($entry.vm)/deallocate?api-version=2024-11-01"
        if ($result.StatusCode -notin @(200,202)) { $failed += $entry.vm }
        Write-Output "Deallocate $($entry.vm) HTTP=$($result.StatusCode)"
    } catch { $failed += $entry.vm }
}
if ($failed.Count) { throw "Deallocation failed for $($failed -join ',')" }
