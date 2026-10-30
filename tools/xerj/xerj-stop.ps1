# Stop the local XERJ node started by xerj-start.ps1.
# Only the recorded pid is touched; data and indexes are kept.
[CmdletBinding()]
param()

. "$PSScriptRoot\xerj-env.ps1"

$state = Get-XerjState
if (-not $state) {
    Write-Output "No XERJ node state file; nothing to stop."
    exit 0
}

$process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
if (-not $process -or $process.ProcessName -ne 'xerj') {
    Write-Output "Recorded pid $($state.pid) is not a running xerj process; removing stale state file."
    Remove-Item -LiteralPath $XerjStateFile -Force
    exit 0
}

$recordedStart = [datetime]::Parse($state.startedAt, [System.Globalization.CultureInfo]::InvariantCulture)
if ([math]::Abs(($process.StartTime - $recordedStart).TotalSeconds) -gt 120) {
    throw "PID $($state.pid) is an xerj process but its start time does not match the recorded node; refusing to stop it. Remove $XerjStateFile manually after checking."
}

Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
$deadline = (Get-Date).AddSeconds(10)
while ((Get-Process -Id $process.Id -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 200
}

if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    $forceDeadline = (Get-Date).AddSeconds(5)
    while ((Get-Process -Id $process.Id -ErrorAction SilentlyContinue) -and (Get-Date) -lt $forceDeadline) {
        Start-Sleep -Milliseconds 200
    }
}

if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
    throw "xerj process $($process.Id) is still running after stop."
}

Remove-Item -LiteralPath $XerjStateFile -Force
Write-Output "XERJ node stopped (pid $($process.Id)). Data and indexes were kept."
