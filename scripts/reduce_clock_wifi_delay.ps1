param([string]$IdentityFile,[string]$SourceRevision='uncommitted')
$ErrorActionPreference='Stop'
$taskRun=(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'current-run.txt') -Raw).Trim()
$taskName=Split-Path -Leaf $taskRun
$taskSSH=Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'
$taskSCP=Join-Path $env:SystemRoot 'System32\OpenSSH\scp.exe'
$taskState=@{stage='disable wifi sleep';source_revision=$SourceRevision;steps=@();status='running';clock_services_restarted=$false;robot_motion_commands=0}
function Save-State { $taskState | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskRun 'wifi_prepare_result.json') -Encoding UTF8 }
try {
    $taskPayload=[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'clock_wifi_prepare.sh')))
    foreach($taskSpec in @(@{name='ras1';ip='192.168.137.186';folder='leader'},@{name='ugrp1';ip='192.168.137.218';folder='follower'})){
        $taskNameHost=$taskSpec.name; $taskRemote='/home/'+$taskNameHost+'/ugrp_clock_logs/'+$taskName
        $taskArgs=@('-o','StrictHostKeyChecking=yes','-o',('HostKeyAlias='+$taskNameHost+'.local'),'-o','ConnectTimeout=8','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=3')
        if($IdentityFile){$taskArgs+=@('-i',$IdentityFile,'-o','IdentitiesOnly=yes')}
        Save-State
        Write-Host ('--- '+$taskNameHost+' Wi-Fi sleep setting ---')
        $taskCommand="printf '%s' '$taskPayload' | base64 -d > '$taskRemote/clock_wifi_prepare.sh' && sudo bash '$taskRemote/clock_wifi_prepare.sh' '$taskNameHost' '$taskRemote'"
        & $taskSSH @taskArgs -v -E (Join-Path $taskRun ($taskNameHost+'_wifi.ssh.log')) -tt ($taskNameHost+'@'+$taskSpec.ip) $taskCommand
        $taskCode=$LASTEXITCODE
        $taskState.steps+=@{host=$taskNameHost;stage='apply';exit_code=$taskCode}; Save-State
        & $taskSCP @taskArgs -r ($taskNameHost+'@'+$taskSpec.ip+':'+$taskRemote+'/wifi-latency') (Join-Path $taskRun $taskSpec.folder)
        $taskRetrieve=$LASTEXITCODE
        $taskState.steps+=@{host=$taskNameHost;stage='retrieve';exit_code=$taskRetrieve}; Save-State
        if($taskCode -ne 0 -or $taskRetrieve -ne 0){throw 'Wi-Fi setting or retrieval failed; see logs'}
    }
    $taskState.status='wifi_sleep_disabled_both'
} catch { $taskState.status='failed_or_partial';$taskState.error=$_.Exception.Message;Write-Host $taskState.error -ForegroundColor Red }
finally {Save-State;Write-Host ('Saved: '+$taskRun)}
if($taskState.status -ne 'wifi_sleep_disabled_both'){exit 1}
