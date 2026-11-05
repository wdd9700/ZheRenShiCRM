# Windows 试用客户端：SSH 回环隧道 + Edge「安装此站点为应用」

**状态：实现候选；真实隧道、浏览器登录、Edge「安装为应用」与独立窗口启动已实测通过，卸载与离线仍未验证。** 2026-11-02 用本机 Edge 以真实表单登录 Administrator，通过 Edge 的「安装此站点为应用」生成 Windows 应用条目（AppsFolder `frappe crm`），关闭后从安装入口重新启动为无地址栏独立窗口，登录态保持（详见 §10）。仍是单人合成数据试用，不是生产/团队上线；团队权限未验收，本文不声称原生安装包。

- 启动脚本：`deploy/windows/start-tunnel.ps1`
- 启动快捷方式（可选）：`deploy/windows/new-shortcut.ps1`（只创建 .lnk，不安装应用）
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

- origin（协议 + 主机 + 端口）决定**安装身份、Web Storage/缓存与 Service Worker 作用域**：`127.0.0.1:18088`、`127.0.0.1:8088`、`localhost:18088` 属于三个不同的应用/存储身份。
- **Cookie 不按端口隔离**：Cookie 按主机/域、路径与属性匹配。`http://127.0.0.1:8088` 与 `http://127.0.0.1:18088` 共用主机 `127.0.0.1`，同名 Cookie（尤其会话 `sid`）可能互相覆盖。因此本机 WSL 的 8088 与隧道的 18088 不要放在同一个浏览器配置里混用；建议为本试用使用独立的 Edge 配置（profile），不要仅靠端口隔离会话。
- 本地端口仍写死为 `18088`，没有「换端口」参数；18088 被占用时脚本**明确拒绝启动**，不会静默改端口或改 origin。换端口会改变安装身份与存储（需重装应用），但**不会**自动让 Cookie 按端口隔离。
- 不用本机 8088 做入口：本机 WSL 沙箱的 8088 已用于本地验证；与 18088 只是端口不同，Cookie 仍同主机共享，混用会互相影响。
- 用回环 HTTP 而不是公网直连：`127.0.0.1` 属于浏览器的可信上下文，无需证书即可承载 Web 应用安装与 Service Worker；公网 IP 明文直连既不满足该前提，也不在本试用路径内。生产/团队采用什么入口（域名、证书、备案等）不在本文决定范围。
- 服务器端仍按 `deploy/compose.yml` 只把 `8088` 绑在服务器回环，不对外发布；SSH 只作为到达该回环的通道。

## 3. 前置条件

| 项目 | 要求 | 怎么确认 |
|---|---|---|
| 操作系统 | Windows 10/11 | — |
| 浏览器 | Microsoft Edge（任意近版） | 打开 `edge://version` |
| SSH 客户端 | **Windows 内置 OpenSSH**（`%SystemRoot%\System32\OpenSSH\ssh.exe`）。脚本只支持内置客户端，不回退到 PATH 上的其他 ssh（如 Git 自带的 ssh） | 确认该路径存在；脚本用它并显式传 `-F NUL` |
| 服务器连通性 | 当前试用服务器 `8.133.190.46:22` 可达；正式发布地址由主控提供，用参数传入，不要写死临时地址 | `Test-NetConnection <地址> -Port 22` |
| 服务器 SSH 配置 | 允许密钥登录、`AllowTcpForwarding yes` | 由服务端部署任务确认，本文不假设已就绪 |
| 私钥文件 | 使用者自行准备，只以路径传入；文件 ACL 必须仅本人（及 SYSTEM、Administrators）可读，否则 Windows OpenSSH 会拒绝加载 | 见 §4、§5；脚本不改 ACL |
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
- 私钥同样受 Windows OpenSSH 的权限检查：若文件还对其他用户或组可读（例如继承了共享/沙箱目录的 ACE），ssh 会报 `Bad permissions` 或 `UNPROTECTED PRIVATE KEY FILE`，并拒绝加载私钥。这是 OpenSSH 的安全要求，客户端没有关闭它的选项；脚本不会修改 ACL，也不会复制或移动私钥。请把私钥放在仅你本人（及 SYSTEM、Administrators）可读的位置后重试。
- 若既有私钥只是 ACL 过宽、经明确授权需要就地收紧：先只读记录原 owner/DACL/继承状态（SDDL，不含密钥正文）并保存到本机 ignored runtime，写明精确恢复方法；再仅对**该单个文件**执行 `icacls <该文件> /inheritance:r /grant:r "<你的账号>:F" "NT AUTHORITY\SYSTEM:F" "BUILTIN\Administrators:F"`，修改后核对 owner 未变、DACL 受保护、只剩这三个主体、文件大小与修改时间未变。不要递归、不要改父目录或其他密钥、不要改全局 SSH 配置、不要复制私钥；未获授权时不要自行修改。
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
- 本地端口固定 18088；服务器地址默认 `8.133.190.46`、远端回环端口默认 `8088`（当前服务端约定），可用 `-HostName` / `-RemotePort` 指定。正式发布地址由主控提供后再填入，不在脚本或快捷方式里写死临时地址或凭据。
- **退出**：在这个控制台按 Ctrl+C；关闭窗口同样会断开。ssh 会收到中断退出，若控制台直接回到提示符而没有结尾摘要，属正常。
- **重连**：用同一命令再运行一次。脚本不重试、不换端口、不杀无关进程。
- **只做预检**：加 `-WhatIf`，只检查参数与端口并打印命令，不启动 ssh、不连接服务器。
- **端口被占用**：脚本报错并以退出码 1 结束，提示自行确认占用者（`Get-NetTCPConnection -LocalPort 18088 -State Listen`）。确认是什么进程后再自行处理，不要为了跑通去结束无关进程。
- **私钥有口令**：ssh 会在同一控制台自行提示，口令只交给 ssh；脚本不读取、不保存、不打印口令或私钥。
- 脚本只尝试公钥认证（`PreferredAuthentications=publickey`），不会退回密码登录；服务端只允许密码登录时会直接失败，这是安全边界，不在客户端放宽。
- 如果脚本被 PowerShell 执行策略拦截，可仅对当前窗口临时放宽：`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`（关闭窗口即失效，不改机器级策略）。

### 5.1 创建启动快捷方式（可选）

想让试用更像“点一下就启动”，可用 `deploy/windows/new-shortcut.ps1` 在桌面生成一个**启动器快捷方式**：

```powershell
cd P:\CRM
.\deploy\windows\new-shortcut.ps1 `
  -IdentityFile "$env:USERPROFILE\.ssh\crm_trial_ed25519" `
  -KnownHostsFile "$env:USERPROFILE\.ssh\crm_trial_known_hosts" `
  -ServerAddress 8.133.190.46 -RemotePort 8088
```

- 快捷方式只调用 `start-tunnel.ps1`（前台隧道），**不等于** Edge 的「安装此站点为应用」，也不代表离线客户端；Edge 安装仍需按 §7 手动完成。
- 不创建计划任务或开机自启；默认拒绝覆盖同名快捷方式（需要覆盖时加 `-Force`）。
- 只记录路径、服务器地址与端口，不记录密码或密钥内容；快捷方式可随时删除。
- 正式发布地址由主控提供后用 `-ServerAddress` / `-RemotePort` 传入，不要写死临时端口或凭据。

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

- 期望：`/login` 返回 200；`/crm` 在**已登录**时返回应用页面（匿名时会先被服务端拒绝，见下）。
- 若 ssh 仍在运行但这两个请求超时/连接被重置，问题在服务端应用未就绪（容器未起、8088 未监听），不是客户端。
- 脚本不会替你探测这两个地址，也不会自动打开浏览器，避免把「SSH 已启动」误报成「CRM 已就绪」。

2026-11-01 经本隧道实测（匿名、未加 Host 覆盖）：`/api/method/ping` → 200 `{"message":"pong"}`（`application/json`，约 0.04s）；`/login` → 200 `text/html`（344,161 字节）；`/app` → 301 到 `/login?redirect-to=%2Fapp`；**匿名 `/crm` → 403「Not Permitted」**（浏览器 Accept/UA 下相同），这是服务端对该路由的匿名处理，不是隧道或端口问题。因此匿名直接打开 `/crm` 不会跳登录，请按 §7 先登录。

## 7. 用 Edge 安装为应用（真实步骤）

1. 保持隧道运行，用 Edge 打开 `http://127.0.0.1:18088/login?redirect-to=/crm`（或 `http://127.0.0.1:18088/login`）。**匿名直接打开 `/crm` 当前返回 403「Not Permitted」，不会跳登录**（2026-11-01 实测）。
2. 用你自己的 CRM 账号在页面表单登录（不要注入 Cookie 或 sid），登录成功后进入 `http://127.0.0.1:18088/crm`。若提示「登录无效」，先确认密码框里的位数与实际一致（自动粘贴可能丢字符），用键盘重新输入一次再试。
3. 登录后在地址栏右侧点「安装 Frappe CRM」图标（或 `⋯ → 应用 → 将此站点作为应用安装`）。Edge 会弹出「安装应用」确认框，发布者显示 `127.0.0.1:18088`，可勾选固定到任务栏 / 开始屏幕 / 桌面快捷方式 / 登录时自动启动——本流程默认**不勾选**自动启动，其余按你意愿。
4. 确认后 Edge 立即打开独立应用窗口，`edge://apps` 的「已安装的应用」出现 Frappe CRM 卡片；Windows 应用列表（AppsFolder）里也有条目，可从开始菜单启动。
5. 关闭应用窗口后再从开始菜单/`edge://apps` 的「打开」重新启动，验证仍是独立窗口（无地址栏、无标签页），登录态由同一 Edge 配置保持（2026-11-02 实测通过）。注意 Cookie 按主机而非端口匹配：不要在同一 Edge 配置里同时访问本机 8088 等其他 `127.0.0.1` 站点，建议用独立配置跑本试用。
6. 若 Edge 不提供安装入口：先按 §6 确认页面真实可用，再检查服务端是否返回了 manifest；此时也可以继续当普通网页使用。**不要**用 `msedge --app=...` 或 `.lnk/.url` 快捷方式冒充「安装」——那只是快捷方式，不是应用安装。

## 8. 在线依赖与试用限制

- **必须隧道在线**：SSH 断开、电脑睡眠唤醒、网络切换后应用打不开；重新运行脚本即可恢复，不需要重装应用。
- **不承诺离线**：Service Worker 是否存在、作用范围是否覆盖 `/crm` 均未验证；即使存在，也不代表可以离线使用。
- **没有客户端更新器**：更新来自服务端重新部署。看到旧界面时，在应用窗口内按 `Ctrl+Shift+R` 强制刷新。
- **登录态**：Cookie 按主机 `127.0.0.1` 匹配（**不按端口**），由 Edge 该配置保存。2026-11-02 实测：关闭应用窗口后重新从安装入口启动，仍保持 Administrator 登录；最终以服务端会话过期策略为准。同一 Edge 配置里访问本机其它 `127.0.0.1` 端口的站点可能覆盖同名 `sid`，建议用独立 Edge 配置跑本试用；不同 Windows 用户、不同 Edge 配置互不共享。
- **数据边界**：团队权限隔离仍未通过验收（见 `docs/TEAM_ACCESS.md`、`docs/MVP_WORKFLOW.md` §7），**只用合成数据试用，不要放真实客户资料**。
- **回环端口不是身份边界**：本机任何进程都能访问 18088，权限仍只由 CRM 登录与角色决定。
- **不做开机自启**：本方案不创建计划任务或系统服务；Edge 应用自带的「登录时启动」开关也不由本流程开启，需要时由你自行决定。

## 9. 卸载与清理

- **卸载应用**：`edge://apps` → 应用卡片 → `Uninstall`（或右键卸载）。开始菜单/任务栏项应随之移除。Windows「设置 → 应用」是否出现条目未验证，出现与否如实记录。（卸载行为本身未实测。）
- **启动快捷方式**：删除 `new-shortcut.ps1` 创建的 `.lnk` 即可；它不注册服务、不写注册表、不设自启，删除不影响已安装的 Edge 应用。
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

未验证（仍需进一步操作或服务端配合才能完成）：

- Service Worker 的实际作用范围与离线能力；manifest 当前以 `application/octet-stream` 返回（2026-11-02 观测），不影响本次安装，但离线/缓存行为未验证。
- 卸载行为、Edge「设置 → 应用」是否出现条目。
- 固定到任务栏/开始屏幕（本流程未勾选）、断线负例、非管理员 Windows 账户下的行为。
- 匿名 `/crm` 返回 403 是否为本部署的预期行为（需服务端确认；客户端不掩盖、不加 Host 覆盖）。

### 2026-11-01 真实连接尝试（未通过：卡在本机私钥权限）

准备与预检（均已实测）：

- `Test-NetConnection 8.133.190.46 -Port 22` = True。
- 专用 known_hosts 只有一条 `256 SHA256:JHFV75F2oc1tYqjd4viv130aknkd7fOwtKEpmGtgy80 8.133.190.46 (ED25519)`，与提供值一致。
- 18088 启动前空闲；`-WhatIf` 通过并显示 `-F NUL`、strict、显式 known_hosts 与固定转发参数。

实际启动后 ssh 在认证前退出 255，原始错误要点：

```
Bad permissions. Try removing permissions for user: 550C-wdd9700\CodexSandboxUsers ... on file <私钥>
WARNING: UNPROTECTED PRIVATE KEY FILE!
This private key will be ignored.
Load key "<私钥>": bad permissions
dev@8.133.190.46: Permission denied (publickey,...)
```

- 结论：TCP 22 与主机密钥校验均已通过，失败点是**本机私钥文件 ACL 过宽**（继承了 `CodexSandboxUsers` 与一个未知 SID 的 ReadAndExecute ACE），不是网络、端口或服务器问题。
- 本轮未建立隧道；未修改任何 ACL、未复制或读取私钥、未启用 ssh-agent、未改用其他 ssh 实现、未重复启动进程；18088 仍空闲。
- 处理要求：把私钥放到仅本人（及 SYSTEM、Administrators）可读的位置后，用同一命令重试。不复制或移动私钥、不切换其他 ssh 实现绕过该保护；若将来获准修 ACL，须先备份该单个文件的原始 owner/DACL/继承状态（不含私钥正文），只移除非允许读者，并按原文精确恢复，而不是简单重新开启继承。在此之前不宣称隧道或客户端可用。

### 2026-11-01 私钥 ACL 修正（经授权）与真实隧道验证

- 授权范围：仅该单个附件私钥文件；未递归、未改父目录/其他密钥/SSH 配置、未启用 agent、未复制或读取密钥正文、未改用其他 ssh 实现。
- 备份：修改前以只读方式记录 owner/DACL/继承状态（SDDL）到本机 ignored runtime `deploy/.runtime/m12-private-key-acl-backup-20261101.txt`（无密钥正文），文件内写明精确恢复方法（用该 SDDL 重新 `Set-Acl`）。
- 修改：仅对该文件执行 `icacls <该文件> /inheritance:r /grant:r "<账号>:F" "NT AUTHORITY\SYSTEM:F" "BUILTIN\Administrators:F"`。
- 核对：owner 未变（`550C-WDD9700\74090`）；DACL 受保护、继承已断开；只剩 3 个 ACE；文件大小 419 与 LastWriteTime 未变；未自动恢复宽松 ACL。

隧道与匿名 HTTP（未加 Host 覆盖、未登录、未读远端 `.env`、未改服务器）：

| 检查 | 结果 |
|---|---|
| 18088 | 启动前空闲；启动后只监听 `127.0.0.1`（ssh pid 43556，脚本任务 pid 38836） |
| `/api/method/ping` | 200，`{"message":"pong"}`，`application/json`，约 0.04s |
| `/login` | 200，`text/html`，344,161 字节 |
| `/app` | 301 → `/login?redirect-to=%2Fapp` |
| `/crm`（匿名） | 403「Not Permitted」（浏览器 Accept/UA 相同），不是隧道问题 |
| `/login` 页面实际引用 | login.bundle CSS 200 `text/css`；website.bundle CSS 200 `text/css`；frappe-web JS 200 `application/javascript`；`/assets/team_access/access.js` 200 `application/javascript`；`/website_script.js` 200 `text/javascript` |
| known_hosts | 未改写（94 字节、1 条、修改时间不变） |

隧道保留运行供后续浏览器试用：结束脚本（Ctrl+C）或停止对应后台任务、结束 ssh 进程即断开；未创建计划任务或开机自启。本轮的「登录与 Edge 安装未验证」已由下一节补充。

### 2026-11-02 真实浏览器登录、Edge 安装为应用与独立窗口

前置：隧道在久连约 13 小时后曾因 `client_loop: send disconnect: Connection reset` 退出；本轮用同一脚本重建**单一**隧道（仅 `127.0.0.1:18088`，ssh pid 48940、任务 pid 48964），未起重复进程。

- 登录：在用户主 Edge 中先退出既有 Administrator 会话，再经 `/login?redirect-to=/crm` 表单输入账号与密码；粘贴口令曾丢 1 位导致「登录无效」，改为键盘逐位输入后成功。登录后 `/crm/leads/view/list` 正常显示，侧栏为 Administrator，列表可见合成线索 `C010800-REMOTE-20261102…`；未注入 Cookie/sid，未改服务端设置。
- 安装：地址栏出现「应用程序可用。安装 Frappe CRM」，确认框发布者为 `127.0.0.1:18088`；点「安装」后 Edge 弹出「已安装应用」提示（"Frappe CRM 已作为设备上的应用进行安装…从开始菜单、任务栏或桌面启动"）。本流程取消勾选「固定到任务栏」，未勾选开始屏幕/桌面快捷方式/登录时自动启动。
- 结果：`edge://apps` 的「已安装的应用」出现 Frappe CRM 卡片（含描述与「打开」按钮）；Windows AppsFolder 存在条目 `127.0.0.1-D0C192E1_79zy1vv1ew6qc!App`。
- 独立窗口：关闭应用窗口后从该安装入口重新启动，得到标题 `Frappe CRM`、无地址栏/无标签页的独立窗口，仍是 Administrator 登录态（Cookie 按主机 `127.0.0.1` 匹配，不按端口）。
- 未做：卸载、固定到任务栏/开始屏幕、登录时自动启动、离线与断线负例、非管理员账户；不声称生产或团队权限可用。

### 2026-11-05 v1.0 入口补齐（本地验证，无 GUI/服务端操作）

- `start-tunnel.ps1` 新增 `-RemotePort`（默认 8088，范围 1–65535）；本地入口仍固定 18088。`-WhatIf` 显示 `-L 127.0.0.1:18088:127.0.0.1:9000`（测试值），非法 70000 被参数校验拒绝；18088 被占用时仍退出 1。
- 新增 `new-shortcut.ps1`：仅在指定路径创建 `.lnk`（目标为 powershell.exe 运行 start-tunnel.ps1，参数含私钥/known_hosts 路径、地址与端口），默认拒绝覆盖，`-WhatIf` 不写文件。
- 本地测试均写入 `%TEMP%` 后删除：快捷方式目标/工作目录/参数回读正确（含 `-HostName`、`-RemotePort`）；重复创建被拒（exit 1）；缺失私钥被拒（exit 1）。未在桌面/开始菜单创建任何快捷方式，未改动浏览器或服务端。

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
- **已验证**：真实表单登录（注销后重新登录 Administrator）、Edge「安装此站点为应用」、Windows AppsFolder 条目、关闭后从安装入口重启的无地址栏独立窗口，以及隧道/匿名 HTTP 资产。**未验证**：卸载、固定到任务栏/开始屏幕、登录时自启动、离线与 Service Worker 作用范围、断线负例、非管理员账户。因此不声称「完整 GUI 验收」已通过，也不把上述结果扩展为生产可用或团队权限通过。
- 不创建计划任务、开机自启、后台服务；不自动结束无关进程；不静默换端口。
- 不读取、复制、打印私钥内容；不自动接受未知主机密钥；不修改 ACL 或 SSH 全局配置。
- 不读取用户全局 SSH 配置（启动时显式传 `-F NUL`），也不回退到 PATH 上的其他 ssh 实现；不要求使用者先修好 `%USERPROFILE%\.ssh\config` 才能使用本客户端。
- 不新增任何仓库依赖；客户端安装不在本仓库产物内，删除仓库文件不影响 Edge 里已安装的应用（反之亦然）。
