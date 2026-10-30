# Query the local XERJ node with compact passages.
# Default: ranked passages (search). -Def: symbol/definition lookup.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Query,
    [int]$K = 3,
    [int]$Full = 500,
    [switch]$Json,
    [switch]$Def,
    [string]$Lang
)

. "$PSScriptRoot\xerj-env.ps1"

if (-not (Get-XerjNodeProcess)) {
    throw "XERJ node is not running. Start it first: powershell -File tools\xerj\xerj-start.ps1"
}

Set-XerjClientEnv

if ($Def) {
    $queryArgs = @('def', $Query, '--prefix', $XerjPrefix, '-k', "$K")
    if ($Lang) { $queryArgs += @('--lang', $Lang) }
} else {
    $queryArgs = @('search', $Query, '--prefix', $XerjPrefix, '-k', "$K", '--full', "$Full")
    if ($Json) { $queryArgs += '--json' }
}

& $XerjExePath @queryArgs
exit $LASTEXITCODE
