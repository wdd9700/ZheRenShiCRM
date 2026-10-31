# Windows 试用客户端：SSH 回环隧道 + Edge「安装此站点为应用」

**状态：实现候选，端到端未验收。** 本文给出在本机 Windows 上试用 CRM 的具体做法，并逐项区分「已本地验证」与「必须等服务器就绪后人工验证」的部分（见 §10）。它不是生产上线方案，也不代表所有团队权限问题已解决。

- 启动脚本：`deploy/windows/start-tunnel.ps1`
- 客户端形态：Edge 安装的 **Web 应用**（不是 exe / MSIX / 原生安装包）
- 固定 origin：`http://127.0.0.1:18088`
- 远端：`dev@8.133.190.46` → 服务器回环 `127.0.0.1:8088`

## 1. 形态与链路

```
Edge 应用窗口（http://127.0.0.1:18088/crm）
   │
   │  本机 127.0.0.1:18088  ← start-tunnel.ps1 启动的 ssh -L 转发
   ▼
服务器 8.133.190.46:22 ──► 服务器回环 127.0.0.1:8088（compose frontend）
```

脚本只做端口转发：不安装软件、不写系统服务、不建计划任务、不改 SSH 全局配置、不读取/复制/打印私钥内容。启动 ssh 时显式传 `-F NUL`（Windows 空设备 = 空配置），因此**不读取** `%USERPROFILE%\.ssh\config`，也不受其内容或权限影响。隧道在前台运行，Ctrl+C 即结束。

## 2. 固定 origin 契约 `http://127.0.0.1:18088`

- origin 由「协议 + 主机 + 端口」决定：`127.0.0.1:18088`、`127.0.0.1:8088`、`localhost:18088` 是**三个不同的应用身份**，安装记录、Cookie、缓存各自独立。
- 因此本地端口在脚本里写死为 `18088`，没有「换端口」参数；18088 被占用时脚本**明确拒绝启动**，不会静默改端口或改 origin。改端口等于换应用身份，需要重新安装并丢失登录态。
- 不用本机 8088 做入口：本机 WSL 沙箱的 8088 已用于本地验证，两套入口若共用同一 origin 会互相干扰。
- 用回环 HTTP 而不是公网直连：`127.0.0.1` 属于浏览器的可信上下文，无需证书即可承载 Web 应用安装与 Service Worker；公网 IP 明文直连既不满足该前提，也不在本试用路径内。生产/团队采用什么入口（域名、证书、备案等）不在本文决定范围。
- 服务器端仍按 `deploy/compose.yml` 只把 `8088` 绑在服务器回环，不对外发布；SSH 只作为到达该回环的通道。

## 3. 前置条件

| 项目 | 要求 | 怎么确认 |
|---|---|---|
| 操作系统 | Windows 10/11 | — |
| 浏览器 | Microsoft Edge（任意近版） | 打开 `edge://version` |
| SSH 客户端 | **Windows 内置 OpenSSH**（`%SystemRoot%\System32\OpenSSH\ssh.exe`）。脚本只支持内置客户端，不回退到 PATH 上的其他 ssh（如 Git 自带的 ssh） | 确认该路径存在；脚本用它并显式传 `-F NUL` |
| 服务器连通性 | `8.133.190.46:22` 可达 | `Test-NetConnection 8.133.190.46 -Port 22` |
| 服务器 SSH 配置 | 允许密钥登录、`AllowTcpForwarding yes` | 由服务端部署任务确认，本文不假设已就绪 |
| 私钥文件 | 使用者自行准备，只以路径传入 | 见 §4、§5 |
| known_hosts 文件 | 使用者自行准备，路径显式传入且文件须存在 | 见 §4 |
| 本机端口 | `127.0.0.1:18088` 空闲 | `Get-NetTCPConnection -LocalPort 18088 -State Listen` 应为空 |
| 服务端应用 | CRM 已部署并在服务器回环 8088 监听 | 由服务端任务确认；未就绪时客户端无法验收 |

## 4. 准备 known_hosts：主机身份校验不能跳过

脚本固定使用 `StrictHostKeyChecking=yes`，并通过 `-o UserKnownHostsFile="<你的路径>"` 显式指定文件；文件必须已存在。脚本不会自动接受未知主机密钥，不会写全局 `known_hosts`，也不会复制私钥。

同时，ssh 以 `-F NUL` 启动：`NUL` 是 Windows 空设备，等价于一份空用户配置。因此 `%USERPROFILE%\.ssh\config` **完全不参与**本次连接——里面的 `ProxyCommand`、`ProxyJump`、`Match`、额外转发或身份文件都不会生效，其内容与 ACL 也不再是启动前提。这是有意的隔离，不是绕过主机校验：`StrictHostKeyChecking=yes` 与显式 known_hosts 仍然生效。

首次连接前，需要把服务器主机公钥写入专用文件，并且**先核对指纹**：

```powershell
# 1) 取服务器主机公钥。注意：ssh-keyscan 本身未经认证，只能用来抄指纹，不能直接信任。
ssh-keyscan -t ed25519 8.133.190.46

# 2) 通过可信通道核对指纹（例如在服务器控制台执行，或云厂商控制台显示的主机密钥指纹）
#    ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub

# 3) 指纹一致后再写入专用文件；脚本不会创建该文件。
$kh = "$env:USERPROFILE\.ssh\crm_trial_known_hosts"
New-Item -ItemType File -Force -Path $kh | Out-Null
ssh-keyscan -t ed25519 8.133.190.46 | Add-Content -Path $kh
```

- 无法核对指纹时不要继续：未知主机密钥会被 `StrictHostKeyChecking=yes` 拒绝，这是预期行为。
- 不要把现有个人 `known_hosts` 里的其他主机条目混进来当「能连上」的证据；用专用文件更清楚。
- 若 ssh 报 `Bad owner or permissions on ...`，它指向的是本次显式传入的文件（私钥或 known_hosts），**不是**全局 `config`——全局配置已用 `-F NUL` 排除。按系统安全要求修正**那个文件**的权限后重试；`%USERPROFILE%\.ssh\config` 的权限不是使用本客户端的前提，**脚本不会绕过或修改任何 ACL**。

## 5. 启动、退出、重连

```powershell
cd P:\CRM   # 换成你的 checkout 路径
.\deploy\windows\start-tunnel.ps1 `
  -IdentityFile "$env:USERPROFILE\.ssh\crm_trial_ed25519" `
  -KnownHostsFile "$env:USERPROFILE\.ssh\crm_trial_known_hosts"
```

运行后：

- 脚本先做本地预检（两个文件是否存在、18088 是否空闲、内置 ssh 是否存在），打印将要执行的完整 ssh 命令（以 `-F NUL` 开头，只有**路径**，没有私钥内容），然后在前台启动 `ssh -N -T`。
- 本地端口固定 18088、服务器回环端口固定 8088，脚本不提供改端口的参数；`-User`/`-HostName` 默认就是 `dev` / `8.133.190.46`，仅排障时才改，改动后即不对应本文的试用约定。
- **退出**：在这个控制台按 Ctrl+C；关闭窗口同样会断开。ssh 会收到中断退出，若控制台直接回到提示符而没有结尾摘要，属正常。
- **重连**：用同一命令再运行一次。脚本不重试、不换端口、不杀无关进程。
- **只做预检**：加 `-WhatIf`，只检查参数与端口并打印命令，不启动 ssh、不连接服务器。
- **端口被占用**：脚本报错并以退出码 1 结束，提示自行确认占用者（`Get-NetTCPConnection -LocalPort 18088 -State Listen`）。确认是什么进程后再自行处理，不要为了跑通去结束无关进程。
- **私钥有口令**：ssh 会在同一控制台自行提示，口令只交给 ssh；脚本不读取、不保存、不打印口令或私钥。
- 脚本只尝试公钥认证（`PreferredAuthentications=publickey`），不会退回密码登录；服务端只允许密码登录时会直接失败，这是安全边界，不在客户端放宽。
- 如果脚本被 PowerShell 执行策略拦截，可仅对当前窗口临时放宽：`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`（关闭窗口即失效，不改机器级策略）。

退出码约定：

| 退出码 | 含义 |
|---|---|
| 0 | 正常退出（含 `-WhatIf` 预检通过） |
| 1 | 本地前置检查拒绝（路径无效、端口占用、找不到 ssh 等） |
| 255 | ssh 连接/认证/主机校验失败，原始错误见脚本上方输出 |
| 其他 | ssh 自身返回码，原样透传 |

## 6. 验证：隧道建立 ≠ CRM 就绪

隧道窗口里 ssh 不报错，只说明端口转发建立了，**不代表后端 HTTP 可用**。请另开一个窗口确认：

```powershell
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:18088/login
curl.exe -s -o NUL -w "%{http_code}`n" http://127.0.0.1:18088/crm
```

- 期望：`/login` 返回 200；`/crm` 返回 200 或重定向到登录页（具体以服务端实际行为为准，本轮未验证）。
- 若 ssh 仍在运行但这两个请求超时/连接被重置，问题在服务端应用未就绪（容器未起、8088 未监听），不是客户端。
- 脚本不会替你探测这两个地址，也不会自动打开浏览器，避免把「SSH 已启动」误报成「CRM 已就绪」。

## 7. 用 Edge 安装为应用（真实步骤）

1. 保持隧道运行，打开 Edge 访问 `http://127.0.0.1:18088/crm`。
2. 用你自己的 CRM 账号在页面表单登录（不要注入 Cookie 或 sid）。
3. 打开 `⋯（设置及其他） → 更多工具 → 应用 → 将此站点作为应用安装`。地址栏出现安装图标时也可以从那里安装。
4. 打开 `edge://apps`，应看到应用卡片；可「固定到任务栏」「固定到开始菜单」。
5. 从开始菜单或任务栏启动，应为独立窗口、无地址栏。
6. 应用名称是否显示为「Frappe CRM」取决于服务端 manifest 是否可用，本轮未验证；名称不同不影响安装成功与否的判断，以 `edge://apps` 出现卡片、能独立启动为准。
7. 若 Edge 不提供安装入口：先按 §6 确认页面真实可用，再检查服务端是否返回了 manifest；此时也可以继续当普通网页使用。**不要**用 `msedge --app=...` 或 `.lnk/.url` 快捷方式冒充「安装」——那只是快捷方式，不是应用安装。

## 8. 在线依赖与试用限制

- **必须隧道在线**：SSH 断开、电脑睡眠唤醒、网络切换后应用打不开；重新运行脚本即可恢复，不需要重装应用。
- **不承诺离线**：Service Worker 是否存在、作用范围是否覆盖 `/crm` 均未验证；即使存在，也不代表可以离线使用。
- **没有客户端更新器**：更新来自服务端重新部署。看到旧界面时，在应用窗口内按 `Ctrl+Shift+R` 强制刷新。
- **登录态**：Cookie 属于 `http://127.0.0.1:18088` 这个 origin，由 Edge 配置保存。关闭再打开应用是否保持登录未实测，以服务端会话过期策略为准；不同 Windows 用户、不同 Edge 配置互不共享。
- **数据边界**：团队权限隔离仍未通过验收（见 `docs/TEAM_ACCESS.md`、`docs/MVP_WORKFLOW.md` §7），**只用合成数据试用，不要放真实客户资料**。
- **回环端口不是身份边界**：本机任何进程都能访问 18088，权限仍只由 CRM 登录与角色决定。
- **不做开机自启**：本方案不创建计划任务或系统服务；Edge 应用自带的「登录时启动」开关也不由本流程开启，需要时由你自行决定。

## 9. 卸载与清理

- **卸载应用**：`edge://apps` → 应用卡片 → `Uninstall`（或右键卸载）。开始菜单/任务栏项应随之移除。Windows「设置 → 应用」是否出现条目未验证，出现与否如实记录。（卸载行为本身未实测。）
- **断开隧道**：脚本进程结束即释放 18088；确认 `Get-NetTCPConnection -LocalPort 18088 -State Listen` 为空。
- **私钥与 known_hosts**：使用者自己的文件，脚本既不创建也不删除；是否移除由你决定（可能还用于其他 SSH 用途）。
- **没有计划任务、服务或注册表自启项**需要清理。

## 10. 验证状态

已本地执行（2026-10-31，Windows PowerShell 5.1.29695.1001，OpenSSH_for_Windows_9.5p2；未连接远端、未操作 GUI、未安装软件）：

| 检查 | 方法 | 结果 |
|---|---|---|
| 脚本语法 | `Parser::ParseFile` 解析 `deploy/windows/start-tunnel.ps1` | 无错误 |
| 私钥路径不存在 | 传入不存在的 `-IdentityFile` | 明确报错，退出码 1 |
| known_hosts 缺失 | 传入不存在的 `-KnownHostsFile` | 明确报错，退出码 1 |
| 端口占用拒绝 | 本机临时监听 127.0.0.1:18088 后运行脚本 | 拒绝启动、提示固定 origin 不换端口，退出码 1 |
| 只做预检 | `-WhatIf` | 打印完整 ssh 命令，未启动 ssh、未连接服务器，退出码 0 |
| 显式空配置生效 | 本机 `~/.ssh/config` 权限异常时，对比直接 `ssh -G` 与脚本同组选项的 `ssh -G -F NUL` | 不带 `-F` 报 `Bad owner or permissions`、退出 255；带 `-F NUL` 退出 0 且字段按预期解析，证明全局配置未被读取 |
| ssh 参数解析（含带空格路径） | 对脚本同一组选项运行 `ssh -G -F NUL`（known_hosts 路径含空格） | `stricthostkeychecking`、`identitiesonly`、`preferredauthentications=publickey`、`localforward [127.0.0.1]:18088 [127.0.0.1]:8088`、`userknownhostsfile` 均按预期解析 |
| 连接失败报错 | `-HostName 127.0.0.1`（本机，非远端），本机 22 端口拒绝连接 | ssh 原始错误（`Connection refused`）照常显示，脚本给出 255 解释，退出码 255（`-File` 方式运行） |

未验证（必须在服务端就绪后由人工在同一台电脑上执行）：

- 到 `8.133.190.46` 的真实隧道：22 可达、主机密钥核验、密钥认证、`AllowTcpForwarding`。
- `/login`、`/crm` 的真实响应；manifest / Service Worker 的路径、MIME 与作用范围。
- Edge 安装流程、独立窗口、固定到任务栏/开始菜单、登录态保持、断线负例、卸载。
- Edge「设置 → 应用」是否出现条目。
- 非管理员 Windows 账户下的行为。

复现本地检查（可选）：

```powershell
$f = "deploy\windows\start-tunnel.ps1"
$tokens = $null; $errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $f), [ref]$tokens, [ref]$errors)
$errors

.\deploy\windows\start-tunnel.ps1 -IdentityFile <私钥路径> -KnownHostsFile <known_hosts 路径> -WhatIf

# 证明全局配置不参与：即使 ~/.ssh/config 有权限问题，带 -F NUL 的 -G 仍应退出 0
& "$env:SystemRoot\System32\OpenSSH\ssh.exe" -G -F NUL -o StrictHostKeyChecking=yes dev@8.133.190.46
```

## 11. 不做什么、不声称什么

- 不声称是原生安装包、exe 或 MSIX；仓库没有桌面壳或打包依赖。
- 不声称离线可用、后台静默升级或版本回滚。
- 不声称团队/生产可用；团队访问与 HTTPS 入口另行决定。
- 不声称已完成 GUI 验收：本文的「已本地执行」仅覆盖脚本语法和可控失败路径。
- 不创建计划任务、开机自启、后台服务；不自动结束无关进程；不静默换端口。
- 不读取、复制、打印私钥内容；不自动接受未知主机密钥；不修改 ACL 或 SSH 全局配置。
- 不读取用户全局 SSH 配置（启动时显式传 `-F NUL`），也不回退到 PATH 上的其他 ssh 实现；不要求使用者先修好 `%USERPROFILE%\.ssh\config` 才能使用本客户端。
- 不新增任何仓库依赖；客户端安装不在本仓库产物内，删除仓库文件不影响 Edge 里已安装的应用（反之亦然）。
