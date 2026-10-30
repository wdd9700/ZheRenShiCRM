# Show the local XERJ node state without printing the API key.
[CmdletBinding()]
param(
    [switch]$Map
)

. "$PSScriptRoot\xerj-env.ps1"

$state = Get-XerjState
$process = Get-XerjNodeProcess

$processText = if ($process) { "running (pid $($process.Id))" } else { 'not running' }
Write-Output "Node:    $processText"
Write-Output "URL:     $XerjUrl"
Write-Output "Prefix:  $XerjPrefix"
Write-Output "Root:    $XerjIndexRoot"
Write-Output "Runtime: $XerjRuntimeHome"
Write-Output "Data:    $XerjDataDir"
Write-Output "State:   $XerjStateDir"

$listening = @()
foreach ($port in @($XerjPort, ($XerjPort + 1), ($XerjPort + 2))) {
    if (Test-XerjPort -Port $port) { $listening += $port }
}
$expectedPorts = @(($XerjPort), ($XerjPort + 1), ($XerjPort + 2))
Write-Output "Listening: $(if ($listening) { $listening -join ', ' } else { 'none of ' + ($expectedPorts -join '/') })"

if ($state) {
    Write-Output "Logs:    $($state.outLog)"
}

if ($Map) {
    if (-not $process) { throw 'Node is not running; start it before using -Map.' }
    Set-XerjClientEnv
    & $XerjExePath autoindex map --url $XerjUrl --prefix $XerjPrefix
    exit $LASTEXITCODE
}
