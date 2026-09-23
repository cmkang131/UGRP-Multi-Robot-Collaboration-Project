[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$SimulationArguments
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Candidates = @()
if ($env:UGRP_SIM_PYTHON) { $Candidates += $env:UGRP_SIM_PYTHON }
$Candidates += @(
    (Join-Path $ProjectRoot '.venv-sim\Scripts\python.exe'),
    (Join-Path $ProjectRoot '.venv-dev\Scripts\python.exe'),
    (Join-Path (Split-Path -Parent (Split-Path -Parent $ProjectRoot)) '.venv-sim\Scripts\python.exe')
)
$Python = $Candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $Python) {
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($PythonCommand) { $Python = $PythonCommand.Source }
}
if (-not $Python) {
    throw 'Python 3.12 시뮬레이션 환경을 찾지 못했습니다. UGRP_SIM_PYTHON에 python.exe 전체 경로를 지정하세요.'
}

$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = $ProjectRoot
$env:MUJOCO_GL = 'glfw'
if (-not $SimulationArguments -or $SimulationArguments.Count -eq 0) {
    $SimulationArguments = @('start')
}

Push-Location $ProjectRoot
try {
    & $Python -m scripts.sim_cli @SimulationArguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
