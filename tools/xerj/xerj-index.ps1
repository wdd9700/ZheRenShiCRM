# Index P:\CRM under the stable prefix crm-main.
# Dry-run by default. -Apply performs the real autoindex run.
# Incremental update = run -Apply again with the same state dir.
[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$Fresh
)

. "$PSScriptRoot\xerj-env.ps1"

Assert-XerjLayout

if (-not (Get-XerjNodeProcess)) {
    throw "XERJ node is not running. Start it first: powershell -File tools\xerj\xerj-start.ps1"
}

Set-XerjClientEnv

$autoindexArgs = @(
    'autoindex', ('"{0}"' -f $XerjIndexRoot),
    '--url', $XerjUrl,
    '--prefix', $XerjPrefix,
    '--state-dir', ('"{0}"' -f $XerjStateDir),
    '--code-analyzer', 'code',
    '--no-semantic',
    '--no-graph',
    '--workers', '4',
    '--max-file-mb', '10',
    '--max-index-size', '2GB',
    '--max-minutes', '10',
    '--progress', 'plain'
)

if (-not $Apply) {
    $autoindexArgs += '--dry-run'
    Write-Output 'DRY RUN: no index is written. Re-run with -Apply after reviewing the scope.'
}
if ($Fresh) {
    $autoindexArgs += '--fresh'
}

& $XerjExePath @autoindexArgs
$code = $LASTEXITCODE

switch ($code) {
    0 { Write-Output 'autoindex finished: corpus is searchable.' }
    3 { Write-Warning 'autoindex finished with skipped or refused files; review the reasons above.' }
    4 { Write-Warning 'autoindex stopped for a decision; review the plan and re-run with -Apply only after deciding.' }
    default { Write-Warning "autoindex exited with code $code; inspect the node logs and journal." }
}

exit $code
