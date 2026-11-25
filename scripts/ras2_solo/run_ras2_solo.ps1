param(
    [string]$User = '',
    [string]$RobotAddress = '192.168.137.11',
    [ValidateSet('ras2', 'ugrp1')][string]$RobotName = 'ras2',
    [ValidateSet('red', 'cyan')][string]$Target = 'red',
    [switch]$Execute,
    [switch]$Calibrate,
    [ValidateSet('cube', 'published-rectangle')][string]$ObjectShape = 'cube',
    [ValidateRange(1,600)][int]$Seconds = 240
)

$ErrorActionPreference = 'Stop'
if ($Execute -and $Calibrate) { throw 'Choose Execute or Calibrate, not both' }
$project = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$priorAssetRoot = $env:UGRP_SOLO_ROOT
try {
    $env:UGRP_SOLO_ROOT = Join-Path $project 'outputs\ras2-solo-pipeline'
    $actPython = Join-Path $project 'outputs\solo-act-release-20261112\windows-act-venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $actPython)) {
        throw "Existing ACT Python environment missing: $actPython"
    }
    if (-not $User) { $User = Read-Host "$RobotName SSH username" }
    if ($User -notmatch '^[A-Za-z_][A-Za-z0-9_-]*$') { throw 'Invalid SSH username' }
    if ($RobotAddress -notmatch '^[A-Za-z0-9.-]+$') { throw 'Invalid robot address' }

    & $actPython (Join-Path $PSScriptRoot 'source\prepare.py')
    if ($LASTEXITCODE -ne 0) { throw 'Published Solo assets did not verify' }
    & $actPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'ACT dependency check failed' }

    $credential = Read-Host "$RobotName SSH password" -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($credential)
    $helper = Join-Path ([IO.Path]::GetTempPath()) ('ras2-askpass-' + [Guid]::NewGuid().ToString('N') + '.cmd')
    $savedEnvironment = @{}
    $names = @('UGRP_SOLO_SSH_PASSWORD', 'SSH_ASKPASS', 'SSH_ASKPASS_REQUIRE', 'DISPLAY')
    foreach ($name in $names) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    try {
        $env:UGRP_SOLO_SSH_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        [IO.File]::WriteAllText($helper, "@echo off`r`necho(%UGRP_SOLO_SSH_PASSWORD%`r`n", [Text.Encoding]::ASCII)
        $env:SSH_ASKPASS = $helper
        $env:SSH_ASKPASS_REQUIRE = 'force'
        $env:DISPLAY = 'ras2-solo'
        $entryFile = if ($Calibrate) { 'source\calibrate.py' } else { 'source\run.py' }
        $arguments = @((Join-Path $PSScriptRoot $entryFile), '--host', $RobotAddress,
                       '--user', $User, '--expected-host', $RobotName, '--target', $Target, '--seconds', $Seconds)
        if ($Calibrate) {
            Write-Host 'CALIBRATE: supervised arm poses, followed by three requested wheel test pulses.'
            Write-Host 'Use a clear floor. Follow the placement/measurement prompts; no ACT grasp is run.'
        } elseif ($Execute) {
            Write-Host "EXECUTE: $RobotName will move its wheels, arm, gripper and camera."
            Write-Host 'Experimental profile: published SIM camera geometry; nonzero wheel floor 35.'
            $arguments += '--execute'
        } else {
            Write-Host 'CHECK: verify the model, Pi board, camera and live-image inference.'
        }
        if (-not $Calibrate) { $arguments += @('--object-shape', $ObjectShape, '--cube-edge-mm', '30') }
        & $actPython @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Solo run failed. Check the printed log directory.' }
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        foreach ($name in $names) {
            [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
        }
        Remove-Item -LiteralPath $helper -ErrorAction SilentlyContinue
    }
} finally {
    $env:UGRP_SOLO_ROOT = $priorAssetRoot
}
