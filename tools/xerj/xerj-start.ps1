# Start the local XERJ node on loopback only, offline lexical embeddings.
# The node is optional tooling: it is not a prerequisite for CRM work.
[CmdletBinding()]
param(
    [switch]$Foreground
)

. "$PSScriptRoot\xerj-env.ps1"

Assert-XerjLayout

$running = Get-XerjNodeProcess
if ($running) {
    Write-Output "XERJ node already running (pid $($running.Id)) at $XerjUrl"
    exit 0
}

foreach ($port in @($XerjPort, ($XerjPort + 1), ($XerjPort + 2))) {
    if (Test-XerjPort -Port $port) {
        throw "Port $port is already in use. Refusing to auto-pick another port; inspect the listener first."
    }
}

New-Item -ItemType Directory -Force -Path $XerjDataDir, $XerjLogDir, $XerjRunDir, $XerjStateDir | Out-Null

$env:XERJ_DISABLE_FEEDBACK = 'true'

if ($Foreground) {
    & $XerjExePath --data-dir $XerjDataDir --bind 127.0.0.1 --port $XerjPort --no-auto-port --embed-mode lexical --disable-feedback
    exit $LASTEXITCODE
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outLog = Join-Path $XerjLogDir "node-$stamp.out.log"
$errLog = Join-Path $XerjLogDir "node-$stamp.err.log"

$nodeArgs = @(
    '--data-dir', ('"{0}"' -f $XerjDataDir),
    '--bind', '127.0.0.1',
    '--port', "$XerjPort",
    '--no-auto-port',
    '--embed-mode', 'lexical',
    '--disable-feedback'
)

$process = Start-Process -FilePath $XerjExePath -ArgumentList $nodeArgs `
    -RedirectStandardOutput $outLog -RedirectStandardError $errLog `
    -WindowStyle Hidden -PassThru

$deadline = (Get-Date).AddSeconds(30)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) { break }
    if (Test-XerjPort -Port $XerjPort) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 250
}

if (-not $ready) {
    $exited = $process.HasExited
    $status = if ($exited) {
        'process exited before listening'
    } else {
        'process did not listen within 30s and was stopped'
    }
    if (-not $exited) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    }
    throw "XERJ node did not become ready on port $XerjPort ($status). Inspect protected logs: $outLog and $errLog. Log contents are not printed because they may contain a one-time console setup token."
}

$keyDeadline = (Get-Date).AddSeconds(10)
while (-not (Test-Path -LiteralPath $XerjKeyFile -PathType Leaf) -and (Get-Date) -lt $keyDeadline) {
    Start-Sleep -Milliseconds 200
}
if (-not (Test-Path -LiteralPath $XerjKeyFile -PathType Leaf)) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw "Node is listening but $XerjKeyFile was not created. Inspect $errLog."
}

[pscustomobject]@{
    pid       = $process.Id
    url       = $XerjUrl
    bind      = '127.0.0.1'
    embedMode = 'lexical'
    prefix    = $XerjPrefix
    indexRoot = $XerjIndexRoot
    dataDir   = $XerjDataDir
    stateDir  = $XerjStateDir
    outLog    = $outLog
    errLog    = $errLog
    startedAt = (Get-Date).ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath $XerjStateFile -Encoding ASCII

Write-Output "XERJ node started (pid $($process.Id)) at $XerjUrl"
Write-Output "Data: $XerjDataDir"
Write-Output "Logs: $outLog"
Write-Output "Next: xerj-index.ps1 (dry-run) then xerj-index.ps1 -Apply"
