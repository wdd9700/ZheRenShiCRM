# Shared settings for the local XERJ node used by this workspace.
# Dot-source from the other scripts: . "$PSScriptRoot\xerj-env.ps1"
# ASCII only: Windows PowerShell 5.1 reads files without a BOM as ANSI.

$ErrorActionPreference = 'Stop'

$XerjIndexRoot = 'P:\CRM'
$XerjPrefix = 'crm-main'
$XerjPort = 9200
$XerjUrl = "http://127.0.0.1:$XerjPort"

$XerjExePath = if ($env:XERJ_CRM_EXE) {
    $env:XERJ_CRM_EXE
} else {
    Join-Path $env:LOCALAPPDATA 'Programs\xerj\xerj.exe'
}

# Hidden runtime home: excluded from autoindex (dot directory) and from git
# status (.tower/ is listed in .git/info/exclude).
$XerjRuntimeHome = if ($env:XERJ_CRM_HOME) {
    $env:XERJ_CRM_HOME
} else {
    Join-Path $XerjIndexRoot '.tower\xerj'
}

$XerjDataDir = Join-Path $XerjRuntimeHome 'data'
$XerjLogDir = Join-Path $XerjRuntimeHome 'logs'
$XerjRunDir = Join-Path $XerjRuntimeHome 'run'
$XerjStateDir = Join-Path $XerjRuntimeHome "state\$XerjPrefix"
$XerjStateFile = Join-Path $XerjRunDir 'node-state.json'
$XerjKeyFile = Join-Path $XerjDataDir 'admin.key'

function Test-XerjPort {
    param(
        [int]$Port,
        [string]$Address = '127.0.0.1'
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connect = $client.ConnectAsync($Address, $Port)
        if (-not $connect.Wait(300)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Assert-XerjLayout {
    if (-not (Test-Path -LiteralPath $XerjExePath -PathType Leaf)) {
        throw "xerj.exe not found at $XerjExePath. Set XERJ_CRM_EXE to the installed absolute path."
    }
    if (-not (Test-Path -LiteralPath $XerjIndexRoot -PathType Container)) {
        throw "Index root $XerjIndexRoot does not exist."
    }

    # Keep node data and journals outside every indexed path, or under a hidden
    # directory that autoindex always skips. Refuse a visible data dir.
    $rootFull = [System.IO.Path]::GetFullPath($XerjIndexRoot).TrimEnd('\')
    foreach ($pair in @(
        @{ Name = 'data'; Path = $XerjDataDir },
        @{ Name = 'state'; Path = $XerjStateDir },
        @{ Name = 'logs'; Path = $XerjLogDir }
    )) {
        $pathFull = [System.IO.Path]::GetFullPath($pair.Path)
        if ($pathFull.StartsWith($rootFull + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
            $relative = $pathFull.Substring($rootFull.Length + 1)
            if (-not $relative.Split('\')[0].StartsWith('.')) {
                throw "XERJ $($pair.Name) path $($pair.Path) is inside the indexed tree and not hidden. Use a hidden or external runtime home."
            }
        }
    }
}

function Get-XerjApiKey {
    if (-not (Test-Path -LiteralPath $XerjKeyFile -PathType Leaf)) {
        throw "API key file $XerjKeyFile is missing. Start the node once with xerj-start.ps1."
    }
    return (Get-Content -LiteralPath $XerjKeyFile -Raw).Trim()
}

function Set-XerjClientEnv {
    $env:XERJ_URL = $XerjUrl
    $env:XERJ_API_KEY = Get-XerjApiKey
    $env:XERJ_DISABLE_FEEDBACK = 'true'
}

function Get-XerjState {
    if (-not (Test-Path -LiteralPath $XerjStateFile -PathType Leaf)) {
        return $null
    }
    return Get-Content -LiteralPath $XerjStateFile -Raw | ConvertFrom-Json
}

function Get-XerjNodeProcess {
    $state = Get-XerjState
    if (-not $state) { return $null }
    $process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
    if (-not $process -or $process.ProcessName -ne 'xerj') { return $null }
    return $process
}
