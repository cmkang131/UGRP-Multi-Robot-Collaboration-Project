[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Install', 'Login', 'Start', 'Models', 'Test')]
    [string]$Action = 'Models',
    [string]$Model = 'gemini-3.8-flash-high'
)

$ErrorActionPreference = 'Stop'
$Version = '7.2.155'
$InstallDir = Join-Path $env:LOCALAPPDATA 'UGRP\gemini-proxy'
$BinDir = Join-Path $InstallDir 'bin'
$AuthDir = Join-Path $InstallDir 'auth'
$Exe = Join-Path $BinDir 'cli-proxy-api.exe'
$Config = Join-Path $InstallDir 'config.yaml'
$ArchiveName = "CLIProxyAPI_${Version}_windows_amd64.zip"
$ReleaseUrl = "https://github.com/router-for-me/CLIProxyAPI/releases/download/v$Version"

function Assert-Installed {
    if (-not (Test-Path -LiteralPath $Exe)) {
        throw "프록시가 설치되지 않았습니다. 먼저 다음을 실행하세요: .\scripts\gemini_proxy_windows.ps1 Install"
    }
    if (-not (Test-Path -LiteralPath $Config)) {
        throw "설정 파일이 없습니다: $Config"
    }
}

function Test-ProxyPort {
    return $null -ne (Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8391 -State Listen -ErrorAction SilentlyContinue)
}

switch ($Action) {
    'Install' {
        New-Item -ItemType Directory -Force -Path $BinDir, $AuthDir | Out-Null
        $Archive = Join-Path $BinDir $ArchiveName
        $Checksums = Join-Path $BinDir 'checksums.txt'
        Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseUrl/$ArchiveName" -OutFile $Archive
        Invoke-WebRequest -UseBasicParsing -Uri "$ReleaseUrl/checksums.txt" -OutFile $Checksums
        $Line = Get-Content -LiteralPath $Checksums | Where-Object { $_ -match "\s+$([regex]::Escape($ArchiveName))$" } | Select-Object -First 1
        if (-not $Line) { throw "공식 체크섬에서 $ArchiveName 항목을 찾지 못했습니다." }
        $Expected = ($Line -split '\s+')[0].ToLowerInvariant()
        $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
        if ($Actual -ne $Expected) { throw "다운로드 SHA-256이 일치하지 않습니다. expected=$Expected actual=$Actual" }
        Expand-Archive -LiteralPath $Archive -DestinationPath $BinDir -Force
        if (-not (Test-Path -LiteralPath $Exe)) { throw "압축 해제 후 실행 파일을 찾지 못했습니다: $Exe" }
        if (-not (Test-Path -LiteralPath $Config)) {
            $AuthYaml = $AuthDir.Replace('\', '/')
            @(
                'host: "127.0.0.1"'
                'port: 8391'
                "auth-dir: `"$AuthYaml`""
                'api-keys: []'
                'remote-management:'
                '  allow-remote: false'
                '  secret-key: ""'
                '  disable-control-panel: true'
                '  disable-auto-update-panel: true'
                'request-retry: 0'
                'quota-exceeded:'
                '  switch-project: false'
                '  switch-preview-model: false'
            ) | Set-Content -LiteralPath $Config -Encoding utf8
        }
        Write-Host "설치 및 SHA-256 검증 완료: $Exe" -ForegroundColor Green
        Write-Host '다음 단계: .\scripts\gemini_proxy_windows.ps1 Login'
    }
    'Login' {
        Assert-Installed
        & $Exe --config $Config --antigravity-login
        if ($LASTEXITCODE -ne 0) { throw "Google 로그인 프로세스가 종료 코드 $LASTEXITCODE 로 실패했습니다." }
    }
    'Start' {
        Assert-Installed
        if (Test-ProxyPort) { throw '127.0.0.1:8391 포트가 이미 사용 중입니다. 기존 프로세스를 확인하세요.' }
        Write-Host '프록시 실행 중입니다. 이 창을 열어 두고, 종료할 때 Ctrl+C를 누르세요.' -ForegroundColor Cyan
        & $Exe --config $Config
        exit $LASTEXITCODE
    }
    'Models' {
        if (-not (Test-ProxyPort)) { throw '프록시가 실행 중이 아닙니다. 다른 PowerShell 창에서 Start를 실행하세요.' }
        Invoke-RestMethod -Uri 'http://127.0.0.1:8391/v1/models' -Method Get | ConvertTo-Json -Depth 8
    }
    'Test' {
        if (-not (Test-ProxyPort)) { throw '프록시가 실행 중이 아닙니다. 다른 PowerShell 창에서 Start를 실행하세요.' }
        $Body = @{ model = $Model; messages = @(@{ role = 'user'; content = 'Reply with OK.' }); max_tokens = 32 } | ConvertTo-Json -Depth 5
        Invoke-RestMethod -Uri 'http://127.0.0.1:8391/v1/chat/completions' -Method Post -ContentType 'application/json' -Body $Body | ConvertTo-Json -Depth 12
    }
}
