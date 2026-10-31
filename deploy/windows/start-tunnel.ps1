<#
.SYNOPSIS
    Windows 试用客户端：启动到 CRM 服务器的 SSH 回环隧道。

.DESCRIPTION
    把本机 http://127.0.0.1:18088 固定转发到服务器的 127.0.0.1:8088。
    18088 是 Edge 安装的 Web 应用的固定 origin，脚本不提供改端口参数；
    端口被占用即明确失败，不会静默换端口。

    私钥与 known_hosts 只作为外部参数路径传入：脚本不读取、不打印、不复制私钥内容，
    不修改全局 SSH 配置，也不自动接受未知主机密钥（StrictHostKeyChecking=yes）。

    脚本在前台运行 ssh -N，按 Ctrl+C 结束；不创建计划任务、开机自启或后台服务，
    不结束其他进程。ssh 启动成功只代表端口转发就绪，不代表 CRM 已可用。

.PARAMETER IdentityFile
    私钥文件路径，由使用者自行准备。脚本只把它作为 ssh -i 参数。

.PARAMETER KnownHostsFile
    显式 known_hosts 文件路径，文件必须已存在；主机密钥须事先核验并写入。

.PARAMETER User
    服务器登录用户，默认 dev。

.PARAMETER HostName
    服务器地址，默认 8.133.190.46。

.EXAMPLE
    .\start-tunnel.ps1 -IdentityFile "$env:USERPROFILE\.ssh\crm_trial_ed25519" `
                       -KnownHostsFile "$env:USERPROFILE\.ssh\crm_trial_known_hosts"

.EXAMPLE
    # 仅做本地预检并打印将要执行的 ssh 命令，不启动 ssh、不连接远端
    .\start-tunnel.ps1 -IdentityFile <路径> -KnownHostsFile <路径> -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)]
    [string]$IdentityFile,

    [Parameter(Mandatory = $true)]
    [string]$KnownHostsFile,

    [string]$User = 'dev',

    [string]$HostName = '8.133.190.46'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$LocalPort = 18088
$RemotePort = 8088
$LocalOrigin = "http://127.0.0.1:$LocalPort"

function Resolve-RequiredFile {
    param(
        [string]$Label,
        [string]$Path
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "$Label 为空。请传入明确的文件路径，脚本不会猜测默认位置。"
    }
    if ($Path.Contains('"')) {
        throw "$Label 路径包含双引号，无法安全传给 ssh。"
    }

    $full = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path)
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw "$Label 不存在或不是文件：$full"
    }

    return $full
}

function Test-LoopbackPortBusy {
    param([int]$Port)

    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $false
    }
    catch [System.Net.Sockets.SocketException] {
        return $true
    }
    finally {
        if ($null -ne $listener) {
            try { $listener.Stop() } catch { }
        }
    }
}

function Find-SshClient {
    $candidate = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh.exe'
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        return $candidate
    }

    $command = Get-Command -Name 'ssh.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -ne $command) {
        return $command.Source
    }

    throw '未找到 Windows OpenSSH 客户端 ssh.exe。请在“设置 → 系统 → 可选功能”确认已安装 OpenSSH 客户端；本脚本不会自动安装软件。'
}

try {
    $identity = Resolve-RequiredFile -Label 'IdentityFile（私钥路径）' -Path $IdentityFile
    $knownHosts = Resolve-RequiredFile -Label 'KnownHostsFile（known_hosts 路径）' -Path $KnownHostsFile
    $ssh = Find-SshClient

    if (Test-LoopbackPortBusy -Port $LocalPort) {
        throw @"
本机 127.0.0.1:$LocalPort 已被占用，拒绝启动。
客户端固定 origin 是 $LocalOrigin；换端口等于换应用身份（要重装、丢登录态），脚本不会静默改端口。
请自行确认占用者，例如：Get-NetTCPConnection -LocalPort $LocalPort -State Listen
脚本不会替你结束任何进程。
"@
    }

    $sshArguments = @(
        '-N'
        '-T'
        '-o', 'ExitOnForwardFailure=yes'
        '-o', 'ConnectTimeout=15'
        '-o', 'ServerAliveInterval=30'
        '-o', 'ServerAliveCountMax=3'
        '-o', 'StrictHostKeyChecking=yes'
        '-o', 'IdentitiesOnly=yes'
        '-o', 'PreferredAuthentications=publickey'
        '-o', "UserKnownHostsFile=`"$knownHosts`""
        '-i', $identity
        '-L', "127.0.0.1:${LocalPort}:127.0.0.1:${RemotePort}"
        "$User@$HostName"
    )

    Write-Host "本地入口：$LocalOrigin  ->  服务器 127.0.0.1:$RemotePort（$User@$HostName）"
    Write-Host '按 Ctrl+C 结束隧道；重新连接就用相同参数再运行一次。'
    Write-Host '注意：ssh 隧道建立只代表端口转发，不代表 CRM 已就绪；请在入口地址上确认页面实际可用。'
    Write-Host ''

    $target = "$User@$HostName"
    $operation = "建立 SSH 隧道 127.0.0.1:$LocalPort -> 127.0.0.1:$RemotePort"
    $fullCommand = "`"$ssh`" $($sshArguments -join ' ')"

    if (-not $PSCmdlet.ShouldProcess($target, $operation)) {
        Write-Host "将执行：$fullCommand"
        Write-Host '（-WhatIf 预检通过：仅打印命令，未启动 ssh，未连接服务器。）'
        exit 0
    }

    Write-Host "启动：$fullCommand"
    & $ssh @sshArguments
    $code = $LASTEXITCODE

    Write-Host ''
    switch ($code) {
        0 {
            Write-Host 'ssh 已正常退出（退出码 0），隧道关闭。'
        }
        255 {
            Write-Host 'ssh 退出码 255：连接失败。常见原因是网络不可达、22 端口不通、主机密钥不在 KnownHostsFile 中或与记录不符、私钥未被接受。'
            Write-Host '具体原因以上方 ssh 原始输出为准；脚本不重试、不换端口、不改主机校验。'
        }
        default {
            Write-Host "ssh 退出码 $code，以上方 ssh 原始输出为准。"
        }
    }
    Write-Host '隧道关闭后入口不可用；需要时重新运行本脚本。'
    exit $code
}
catch {
    Write-Host ''
    Write-Host "错误：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
