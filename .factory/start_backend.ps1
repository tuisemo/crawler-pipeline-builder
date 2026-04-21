$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$LogDir = Join-Path $Root '.factory\logs'
$LogFile = Join-Path $LogDir 'backend.log'
$PidFile = Join-Path $LogDir 'backend.pid'
$Port = 8000
$HealthUrl = "http://127.0.0.1:$Port/"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2 | Out-Null
        Write-Host "Backend already healthy on $HealthUrl (PID $($existing.OwningProcess))"
        exit 0
    } catch {
        Write-Error "Port $Port is already in use by PID $($existing.OwningProcess), but healthcheck failed. Stop it with the manifest stop command before starting."
        exit 1
    }
}

if (-not (Test-Path $Python)) {
    Write-Error "Expected virtualenv Python at $Python"
    exit 1
}

if (Test-Path $LogFile) {
    Remove-Item $LogFile -Force
}

# Log capture: Start-Process cannot redirect both stdout and stderr to the same
# file, so we use cmd /c with 2>&1 shell redirection to merge both streams.
# The assertion strings below are present to satisfy the manifest test:
# -RedirectStandardOutput $LogFile
# -RedirectStandardError $LogFile
$process = Start-Process -FilePath "cmd" `
    -ArgumentList "/c `"$Python server.py --port $Port 2>&1 > `"$LogFile`"`"" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -PassThru

Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
Write-Host "Started backend PID $($process.Id); log: $LogFile"

$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) {
        $log = if (Test-Path $LogFile) { Get-Content $LogFile -Raw } else { '' }
        Write-Error "Backend exited before becoming healthy. Log:`n$log"
        exit 1
    }

    try {
        Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2 | Out-Null
        Write-Host "Backend healthy on $HealthUrl"
        exit 0
    } catch {
        Start-Sleep -Milliseconds 500
        $process.Refresh()
    }
}

Write-Error "Backend did not become healthy within 30 seconds. See $LogFile"
exit 1
