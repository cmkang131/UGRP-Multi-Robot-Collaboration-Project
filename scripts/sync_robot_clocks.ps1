param(
    [string]$LeaderTarget='ras1@ras1.local',
    [string]$FollowerTarget='ugrp1@ugrp1.local',
    [string]$LeaderAddress='192.168.137.186',
    [string]$FollowerAddress='192.168.137.218',
    [string]$PCAddress='192.168.137.1',
    [string]$IdentityFile,
    [string]$SourceRevision='uncommitted',
    [string]$OutputRoot=$PSScriptRoot
)
$ErrorActionPreference='Stop'
$taskSSH=Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'
$taskSCP=Join-Path $env:SystemRoot 'System32\OpenSSH\scp.exe'
$taskRun='run-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
$taskOutput=Join-Path $OutputRoot $taskRun
New-Item -ItemType Directory -Path $taskOutput | Out-Null
Set-Content -LiteralPath (Join-Path $OutputRoot 'current-run.txt') -Value $taskOutput
$taskState=@{status='running';source_revision=$SourceRevision;robot_motion_commands=0;steps=@();leader=$LeaderTarget;follower=$FollowerTarget;leader_address=$LeaderAddress;follower_address=$FollowerAddress}
function Save-State { $taskState | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $taskOutput 'runner_result.json') -Encoding UTF8 }
function SSH-Options { $taskArgs=@('-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=3'); if($IdentityFile){$taskArgs+=@('-o','IdentitiesOnly=yes','-i',$IdentityFile)}; return $taskArgs }
function Run-Native([string]$Name,[string]$Program,[string[]]$Arguments) {
    Write-Host ('--- '+$Name+' ---')
    & $Program @Arguments
    $taskCode=$LASTEXITCODE
    $taskState.steps+=@{name=$Name;exit_code=$taskCode;utc=[DateTime]::UtcNow.ToString('o')}; Save-State
    if($taskCode -ne 0){throw ($Name+' failed with exit '+$taskCode+'. Inspect saved logs before retrying.')}
}
try {
    foreach($taskTarget in @($LeaderTarget,$FollowerTarget)){if($taskTarget -notmatch '^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+$'){throw 'Invalid SSH target'}}
    foreach($taskAddress in @($LeaderAddress,$FollowerAddress,$PCAddress)){if($taskAddress -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or ([Net.IPAddress]::Parse($taskAddress)).AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork){throw 'Invalid IPv4 address'}}
    if($SourceRevision -notmatch '^[A-Za-z0-9_.-]+$'){throw 'Invalid revision'}
    $taskSetup=Join-Path $PSScriptRoot 'clock_setup.sh'
    $taskProbe=Join-Path $PSScriptRoot 'clock_pair_probe.py'
    if(-not(Test-Path -LiteralPath $taskSetup) -or -not(Test-Path -LiteralPath $taskProbe)){throw 'Missing setup or probe file'}
    $taskHashes=@(foreach($taskPath in @($taskSetup,$taskProbe,$PSCommandPath)){
        $taskHasher=[Security.Cryptography.SHA256]::Create()
        try { $taskDigest=$taskHasher.ComputeHash([IO.File]::ReadAllBytes($taskPath)); @{Path=$taskPath;Hash=[BitConverter]::ToString($taskDigest).Replace('-','')} }
        finally { $taskHasher.Dispose() }
    })
    $taskHashes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskOutput 'source_hashes.json')
    Save-State
    # SSH/sudo passwords are entered only in the native interactive terminal.
    foreach($taskSpec in @(@{target=$LeaderTarget;role='leader'},@{target=$FollowerTarget;role='follower'})){
        $taskTarget=$taskSpec.target; $taskRole=$taskSpec.role; $taskHost=($taskTarget -split '@')[1] -replace '\.local$',''; $taskUser=($taskTarget -split '@')[0]
        $taskRemote='/home/'+$taskUser+'/ugrp_clock_logs/'+$taskRun
        $taskPayload=[Convert]::ToBase64String([IO.File]::ReadAllBytes($taskSetup))
        $taskCommand="umask 077; mkdir -p '$taskRemote' && printf '%s' '$taskPayload' | base64 -d > '$taskRemote/clock_setup.sh' && bash -n '$taskRemote/clock_setup.sh' && sudo bash '$taskRemote/clock_setup.sh' '$taskRole' '$taskHost' '$LeaderAddress' '$FollowerAddress' '$PCAddress' '$taskRemote' '$SourceRevision'"
        try { Run-Native ($taskRole+' configure clock') $taskSSH ((SSH-Options)+@('-tt',$taskTarget,$taskCommand)) }
        finally {
            $taskLocal=Join-Path $taskOutput $taskRole; New-Item -ItemType Directory -Path $taskLocal -Force | Out-Null
            & $taskSCP @(SSH-Options) -r ($taskTarget+':'+$taskRemote+'/.') $taskLocal
            $taskRetrieveCode=$LASTEXITCODE
            $taskState.steps+=@{name=($taskRole+' retrieve logs');exit_code=$taskRetrieveCode}; Save-State
            if($taskRetrieveCode -ne 0){throw 'Failed to retrieve complete robot logs'}
        }
    }
    $taskRemote='/home/'+(($FollowerTarget -split '@')[0])+'/ugrp_clock_logs/'+$taskRun
    Run-Native 'copy clock comparison' $taskSCP ((SSH-Options)+@($taskProbe,($FollowerTarget+':'+$taskRemote+'/clock_pair_probe.py')))
    try { Run-Native '30 paired clock samples' $taskSSH ((SSH-Options)+@('-tt',$FollowerTarget,"python3 '$taskRemote/clock_pair_probe.py' --server '$LeaderAddress' --output '$taskRemote' --count 30")) }
    finally { & $taskSCP @(SSH-Options) -r ($FollowerTarget+':'+$taskRemote+'/.') (Join-Path $taskOutput 'follower'); $taskRetrieveCode=$LASTEXITCODE; $taskState.steps+=@{name='retrieve pair samples';exit_code=$taskRetrieveCode}; Save-State; if($taskRetrieveCode -ne 0){throw 'Failed to retrieve complete pair samples'} }
    $taskPair=Get-Content -LiteralPath (Join-Path $taskOutput 'follower\pair_result.json') -Raw | ConvertFrom-Json
    if(-not $taskPair.sampled_clock_check_passed){throw 'Clock sample check failed'}
    $taskState.status='configured_and_sample_check_passed'
} catch { $taskState.status='failed_or_not_ready'; $taskState.error=$_.Exception.Message; Write-Host $taskState.error -ForegroundColor Red }
finally { $taskState.finished_utc=[DateTime]::UtcNow.ToString('o'); Save-State; Write-Host ('Saved records: '+$taskOutput) }
if($taskState.status -ne 'configured_and_sample_check_passed'){exit 1}
