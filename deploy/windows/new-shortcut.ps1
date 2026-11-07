<#
.SYNOPSIS
    创建一个启动快捷方式：用 start-tunnel.ps1 打开到 CRM 服务器的 SSH 回环隧道。

.DESCRIPTION
    只在指定路径创建 .lnk 快捷方式。它启动的是本仓库的隧道脚本，不是应用安装：
    Edge 的「安装此站点为应用」仍需在浏览器中手动完成，本脚本不会代替。
    脚本不运行隧道、不创建计划任务或开机自启、不修改浏览器设置、不复制私钥；
    快捷方式只记录路径、服务器地址与端口，不记录密码或密钥内容。

.PARAMETER IdentityFile
    私钥文件路径，转发给 start-tunnel.ps1 的 -IdentityFile。

.PARAMETER KnownHostsFile
    专用 known_hosts 路径，转发给 start-tunnel.ps1 的 -KnownHostsFile。

.PARAMETER ServerAddress
    服务器地址，默认当前试用服务器 8.133.190.46；正式发布地址由主控提供后传入。

.PARAMETER RemotePort
    服务器回环上 CRM 监听的端口，默认 8088。本地入口端口始终为 18088。

.PARAMETER ShortcutPath
    快捷方式保存位置，默认桌面上的「Frappe CRM 隧道.lnk」。

.PARAMETER Force
    允许覆盖已存在的同名快捷方式。默认拒绝覆盖。

.EXAMPLE
    .\new-shortcut.ps1 -IdentityFile "$env:USERPROFILE\.ssh\crm_trial_ed25519" `
                       -KnownHostsFile "$env:USERPROFILE\.ssh\crm_trial_known_hosts"
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$IdentityFile,

    [Parameter(Mandatory = $true)]
    [string]$KnownHostsFile,

    [string]$ServerAddress = '8.133.190.46',

    [ValidateRange(1, 65535)]
    [int]$RemotePort = 8088,

    [string]$User = 'dev',

    [string]$ShortcutPath = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Frappe CRM 隧道.lnk'),

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-RequiredFile {
    param(
        [string]$Label,
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "$Label 为空。请传入明确的文件路径。"
    }
    if ($Path.Contains('"')) {
        throw "$Label 路径包含双引号，无法安全写入快捷方式。"
    }

    $full = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw "$Label 不存在或不是文件：$full"
    }

    return $full
}

try {
    if ([string]::IsNullOrWhiteSpace($ServerAddress) -or $ServerAddress -match '[\s"]') {
        throw 'ServerAddress 为空或包含空白/双引号。'
    }
    if ([string]::IsNullOrWhiteSpace($User) -or $User -match '[\s"]') {
        throw 'User 为空或包含空白/双引号。'
    }

    $identity = Resolve-RequiredFile -Label 'IdentityFile（私钥路径）' -Path $IdentityFile
    $knownHosts = Resolve-RequiredFile -Label 'KnownHostsFile（known_hosts 路径）' -Path $KnownHostsFile

    $launcher = Join-Path $PSScriptRoot 'start-tunnel.ps1'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "同目录下未找到 start-tunnel.ps1：$launcher"
    }

    $shortcutFull = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ShortcutPath)
    $shortcutDir = Split-Path -Parent $shortcutFull
    if (-not (Test-Path -LiteralPath $shortcutDir -PathType Container)) {
        throw "快捷方式所在目录不存在：$shortcutDir"
    }
    if ((Test-Path -LiteralPath $shortcutFull) -and -not $Force) {
        throw "快捷方式已存在，未覆盖：$shortcutFull（确认要覆盖时加 -Force）"
    }

    $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath $powershell -PathType Leaf)) {
        throw "未找到 Windows PowerShell：$powershell"
    }

    $arguments = @(
        '-NoProfile'
        '-ExecutionPolicy', 'Bypass'
        '-File', "`"$launcher`""
        '-IdentityFile', "`"$identity`""
        '-KnownHostsFile', "`"$knownHosts`""
        '-User', "`"$User`""
        '-HostName', "`"$ServerAddress`""
        '-RemotePort', "$RemotePort"
    ) -join ' '

    if (-not $PSCmdlet.ShouldProcess($shortcutFull, '创建启动快捷方式')) {
        Write-Host "将创建：$shortcutFull"
        Write-Host "目标：$powershell"
        Write-Host "参数：$arguments"
        Write-Host '（-WhatIf 预检通过：未写入任何文件。）'
        exit 0
    }

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutFull)
    $shortcut.TargetPath = $powershell
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Description = '启动到 CRM 的 SSH 回环隧道（本地入口 http://127.0.0.1:18088）'
    $shortcut.Save()

    if (-not (Test-Path -LiteralPath $shortcutFull -PathType Leaf)) {
        throw "快捷方式创建后未找到文件：$shortcutFull"
    }

    Write-Host "已创建快捷方式：$shortcutFull"
    Write-Host "它只启动隧道脚本，不等于 Edge 的“安装为应用”，也不会开机自启。"
    Write-Host '删除该快捷方式即可移除启动入口，不影响已安装的 Edge 应用或私钥文件。'
}
catch {
    Write-Host ''
    Write-Host "错误：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
