param([ValidateSet('Cost','Force')][string]$Mode = 'Cost', [object]$WebhookData)
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
                Write-Output "Cost query throttled; retry-after=$delay seconds"
                Start-Sleep -Seconds $delay
            }
        }
    } finally { $plain = $null; $token = $null }
}
$subscriptions = @('88b7ee7f-f2f3-4a0d-a0ce-cf7306943676','c02f839a-2a6b-49d8-9c9a-f3d9f09aa5ea')
$stop = $Mode -eq 'Force' -or [DateTime]::UtcNow -ge [DateTime]'2026-11-18T15:00:00Z'
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
$failed = @()
foreach ($sub in $subscriptions) {
    try {
        $path = "/subscriptions/$sub/providers/Microsoft.Compute/virtualMachines?api-version=2024-11-01"
        do {
            $response = Invoke-AzRestMethod -Method GET -Path $path
            if ($response.StatusCode -ne 200) { throw 'VM discovery failed' }
            $data = $response.Content | ConvertFrom-Json
            foreach ($vm in $data.value) {
                $result = Invoke-AzRestMethod -Method POST -Path "$($vm.id)/deallocate?api-version=2024-11-01"
                if ($result.StatusCode -notin @(200,202)) { $failed += $vm.id }
                Write-Output "Deallocate $($vm.id) HTTP=$($result.StatusCode)"
            }
            $path = $data.nextLink -replace '^https://management.azure.com',''
        } while ($path)
    } catch { $failed += $sub }
}
if ($failed.Count) { throw "Deallocation failed for $($failed -join ',')" }
