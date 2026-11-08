# 哲人石CRM Windows 桌面客户端 W020

## 状态与决策

2026-11-09：既有安全壳/两版NSIS工件保留；新源码增加独立 Ed25519 应用签名 OTA 与固定HTTPS入口初始化机制，待独审及真实入口就绪后统一打包。**没有生成生产私钥、没有启用OTA渠道或猜定直连HTTPS地址；现有EXE尚不含此轮新代码。实际GUI安装/覆盖保数据仍因工具缺失未验。** 缺 Windows Authenticode 证书不再被当作应用签名OTA的必要前置，但Windows未知发布者/SmartScreen边界仍存在。

- 用户明确要求真实 EXE、覆盖升级保留客户端数据、预留 OTA，Windows 优先；继续复用团队集中 CRM Web，不新增本地业务数据库。服务端数据、权限和升级归服务端流程，不由安装器迁移。
- 暂选 Electron **45.2.3** + electron-builder **26.18.0** + electron-updater **6.8.11**，Node **22.20.0** / npm **11.6.3**。官方 registry 的 engines 已核，精确版本及 integrity 锁在 `deploy/windows/desktop/package-lock.json`。Edge PWA 不能交付独立 NSIS EXE；Tauri 会增加当前未验证的 Rust/WebView2 构建链，暂不采用。Electron 可替换但体积与升级成本较高。
- M40 设计 brief 与 M41 实现于首次构建前统一冻结身份。此后不因版本、显示名或安装目录变化而修改身份。普通可逆技术选择不再要求用户重复审批；购置证书、受信域名/发布托管及 CI 发布凭据仍属于外部条件，不能自行冒充或购买。
- 根据主控决定，不新增 Windows 系统账户、不提升权限；用明确的 acceptance-only 身份隔离变体进行实际 N→N+1 数据测试，另对生产身份做无冲突的安装/启动最小验证。**变体升级不能证明已有生产身份用户迁移已实测。**
- 图标来自项目自有 `PhilosopherLogo.vue`，精确 M37 commit `4d59623f20d1d677501d5f11fd9d4a5e58ab4823`，中性菱形及三点；无外部 Logo。`build/philosopher.svg` 保留几何源，`scripts/generate-icon.ps1` 用 Windows 内置 System.Drawing 生成 16/24/32/48/64/128/256 多尺寸 ICO 与 PNG，PNG 已通过媒体工具目视检查。保留分发内 `LICENSE.electron.txt`、`LICENSES.chromium.html` 及依赖许可证；自有品牌不改变第三方归属。
- 关键选择已通过 TowerSend 请求主控统一关联 `DECISION_LOG.md`（M41 无该文件写权限）。复评条件：真实安装/连接失败、安全审查发现问题、签名发布渠道落地或未来跨平台需求改变。

## 固定身份及数据契约

| 项目 | 生产值 |
|---|---|
| package.name | `philosopher-stone-crm` |
| appId / AUMID | `com.philosophersstone.crm` |
| executableName | `PhilosopherStoneCRM.exe` |
| 显示名 | 哲人石CRM |
| userData | `%APPDATA%\PhilosopherStoneCRM` |
| sessionData | `%APPDATA%\PhilosopherStoneCRM\browser` |
| 持久会话分区 | `persist:crm` |
| 设置 | userData 下 `settings.json`，`schemaVersion: 1` |
| 本地隧道 origin | `http://127.0.0.1:18088` |

程序为 NSIS **per-user、x64、非 web installer**，不需要管理员安装、不启用开机自启或服务。可选择专用安装目录，程序文件与 AppData 分离。单实例锁防止同用户多进程争用状态。`deleteAppDataOnUninstall=false`，无自定义删除用户数据的安装/卸载 hook；覆盖升级不清 Cookie、Local Storage、IndexedDB 或 Service Worker。卸载后重装仍应保留独立 AppData，但该路径未完成额外实测时不能外推为已验证。

设置先验证再写同目录随机 temp，然后 rename；保留未知字段。旧 `schemaVersion:0`/无版本配置迁移前以不覆盖方式保存 `.pre-v1`，只补默认值/版本，不删旧字段。未知未来版本或损坏 JSON 拒绝启动和覆盖，保留原件供维护；已有迁移备份冲突也保守停止。正常退出及 OTA 前 flush 持久 Cookie/存储；有设置时生成时间戳设置备份。备份可能含本机路径，但不保存 CRM 密码、SSH 私钥正文或 OTA 私钥。

**“不丢数据”边界：** 未提交的表单与 sessionStorage 不属于跨进程持久数据；退出/升级前必须保存。CRM 服务端可撤销会话，Cookie 可过期，首次安装及部分升级后可能正常需要重登。Chromium profile 可能被新版升级，不能承诺旧版 EXE 可直接安全读取已升级 profile。

## 构建与产物

在 Windows PowerShell，从仓库根目录执行（不全局安装）：

```powershell
cd deploy/windows/desktop
npm ci --ignore-scripts --registry=https://registry.npmjs.org
node node_modules/electron/install.js
npm test
npm run dist
npm run dist:next
node scripts/build-acceptance.cjs
node scripts/inspect-artifacts.cjs
```

`npm ci` 按 lock 安装；Electron 安装脚本下载官方发布运行时，builder 按需下载官方 Electron/NSIS/7zip 构建工具缓存。不切换镜像绕过拒绝、不安装全局 NSIS/SDK、不改系统服务。`--publish never` 不发布任何工件；构建文件白名单仅 `src/**`、`package.json` 和固定 OTA policy，不打包 `.env`、密钥、测试或构建日志。生产包启用 ASAR 完整性、OnlyLoadAppFromAsar；关闭 RunAsNode、NODE_OPTIONS、Node CLI inspect fuse。

最终品牌构建第一次在标准 GitHub 下载步骤遇 `ETIMEDOUT 20.205.243.166:443`（274秒），没有换源或关闭 TLS。主控允许使用 builder 官方 `electronDist` 本地输入，复用此前已获准下载的**原始官方归档**，不使用改名/修改 fuse 的旧打包目录。`node scripts/verify-electron-cache.cjs` 从确切官方 URL 对应缓存读取 `electron-v45.2.3-win32-x64.zip`，与精确 Electron npm 包内 `checksums.json`（受 lock integrity 保护）比对，复制后再次核 SHA256：158182975 字节，`489cd061908e697394b004298bf5ffd345c935d10e8ca197ba819f019ab2dec0`。

有此已验缓存时可复现本地输入（路径按 checkout 绝对位置替换，不接受未知归档）：

```powershell
node scripts/verify-electron-cache.cjs
$archive = (Resolve-Path .validation/electron-v45.2.3-win32-x64.zip).Path
npm run dist -- --config.electronDist="$archive"
npm run dist:next -- --config.electronDist="$archive"
node scripts/build-acceptance.cjs --local-electron
node scripts/inspect-artifacts.cjs
```

这是同版本官方分发的标准可配置输入，不是改装 Electron、跳过校验或自造安装器。缺失或 hash 不符立即拒绝；没有缓存时按正常官方下载路径准备。实际 NSIS 默认目录由锁定 AppInfo 的 `executableName` 决定：生产 `%LOCALAPPDATA%\Programs\PhilosopherStoneCRM`，验收为 `...\PhilosopherStoneCRM-Acceptance`；preflight 同时检查这些真实路径及旧兼容命名。早期仅据中文名 fallback 推断“默认目录碰撞”遗漏了 executableName 优先，已纠正，不作为已证缺陷。

输出：

- `dist/PhilosopherStoneCRM-Setup-1.0.0-x64.exe` 与 `.blockmap`
- `dist-next/PhilosopherStoneCRM-Setup-1.0.1-x64.exe` 与 `.blockmap`
- `.validation/acceptance-1.0.0/PhilosopherStoneCRM-Acceptance-Setup-1.0.0-x64.exe`
- `.validation/acceptance-1.0.1/PhilosopherStoneCRM-Acceptance-Setup-1.0.1-x64.exe`

输出与 node_modules 均 gitignored，不提交二进制安装包。交付需同时保存源码 commit、版本、SHA256、签名状态和第三方归属。`inspect-artifacts.cjs` 核四包版本、生产/验收入口、ASAR 与当前生产源逐字节一致（验收 settings 只允许身份后缀差异）、fuse 状态、OTA disabled、生产不含测试入口，并输出各包 SHA256。签名仍需发行流程独立核验，SHA256 不代替签名。

依赖审计：官方 registry `npm audit --omit=dev` 当前 **0 条**；完整 audit **6 moderate**，根因为构建期 `minimatch` 的 glob amplification/拒绝服务（GHSA-g3hv-75wg-m249），影响 builder 及 macOS/Squirrel 关联依赖链。当前使用固定本地构建白名单/NSIS，不把不可信 glob 交给构建器；未运行 `audit fix --force` 盲降整套版本。0 生产 audit 不表示 Electron/Chromium 或全项目无漏洞。最初漏传 registry 的单次 audit 被本机 npmmirror 404 拒绝，已明确改回官方 registry 成功获取结果，不据失败声称安全。

## 本地连接与安全边界

启动先打开本地设置；菜单“连接设置 / 客户端更新”可重开。只在 CRM 标准登录页输入个人 CRM 账号，不嵌入管理员账号、密码或 sid。

1. **客户端管理 SSH**：填管理员提供的主机、个人 SSH 用户、远端回环端口（默认8088）、个人私钥绝对路径、已核验 known_hosts 路径。只将文件路径传给 Windows 内置 `%SystemRoot%\System32\OpenSSH\ssh.exe`；不读取/复制/打印私钥。`spawn` 数组参数、`shell:false`；`-F NUL` 隔离全局用户配置，`GlobalKnownHostsFile=NUL`、严格主机密钥、IdentitiesOnly、公钥专用、BatchMode、超时/keepalive、ExitOnForwardFailure。当前 `IdentityAgent=none`，不启动 agent、不支持隐藏交互式私钥口令；认证失败明确报错，不自动接受未知主机。使用者需自行准备可用个人密钥，不能共享管理员 dev 私钥。
2. **外部隧道**：明确选择该模式，并在每次连接的原生确认框确认18088是本人核验的受信 SSH。客户端不会默默复用一个未知监听者，也不会接管/结束外部隧道。
3. **HTTPS**：仅接受不含路径/查询/用户凭据的 `https://` origin，需独立勾选“已向管理员核验”。使用操作系统/Chromium 正常 TLS 验证，不信任自签/坏证书、不忽略 TLS 错误。

18088 占用时，受管隧道直接拒绝；不换端口、不杀其他 ssh。正常退出只回收本客户端保存的子进程引用。**异常强杀/崩溃后可能遗留自己的 ssh 子进程，未实现 Windows JobObject；不要自动杀进程，须人工核 PID/监听者后处理。** 隧道就绪不代表 CRM 可用；打开页面前还检查 `/api/method/ping` 的 pong 与 `/login` HTML（匿名 `/crm` 可403），再正常导航 `/login?redirect-to=/crm`。

远端 BrowserWindow：`sandbox:true`、`contextIsolation:true`、`nodeIntegration:false`、`webSecurity:true`，**无 preload**。本地设置页有独立临时分区、CSP 与窄方法白名单，主进程同时检查精确 webContents、mainFrame 和本地完整 URL；远端/子框架不能调用设置/更新/文件/exec。设置必须通过 schema 验证。

导航/重定向及网络请求精确限制 origin，WebSocket 只能相应 origin；权限默认拒绝，禁 webview。新窗口同 origin 链接改在当前 CRM 窗口打开，复用持久会话；合法 HTTP(S) 站外链接继续拒绝在应用窗口内导航，但经主进程原生逐次确认后可在系统浏览器打开；拒绝含 URL 凭据、控制字符、file/javascript/data/mailto 或未知协议，无通用 openExternal IPC。不对跨源重定向/子框架自动开外部浏览器。不允许跨域 CDN/外部 OAuth 弹窗，若实际业务需要须另审 origin 与认证边界，不能关闭 webSecurity 凑通。

仅客户端拥有、当前 URL 受信的 CRM webContents 可发起同 origin HTTP attachment 或同 origin blob 下载；原生保存对话框默认用户 Downloads，不进安装树，不自动打开/执行。其它来源的下载拒绝。此限制不等于下载内容无害；用户仍应检查导出文件。

## OTA：应用签名与 Windows 发布者认证分离

2026-11-09 用户明确授权以公私钥实现应用级 OTA；**早期“OTA 必须等待 Authenticode 证书”仅是原策略的选择，不是技术上的唯一方案，现已纠正。** 新增 `pinned-key-ed25519` 策略，使用 Node 内置成熟 Ed25519 能力，不增加密码学依赖、不自行实现算法。原 Authenticode 策略独立保留，不在失败时切换成另一种策略。两种方案都 fail-closed。

- **Ed25519 应用签名**：证明更新清单及安装包是固定私钥持有者授权；不需要先购买 Windows 代码签名证书。
- **Authenticode/SmartScreen**：Windows 认可的发布者身份、系统警告/信誉属于另一层。Ed25519 成功不会把 EXE 变成公信 Windows 已签文件，仍可能显示未知发布者。不能关闭系统保护来冒充已认证。
- 当前 `release/ota-policy.json` 仍为 `{"enabled":false}`；没有生产公钥/获批私钥生成/有效 HTTPS OTA 托管，仍不启用渠道。测试密钥从未写入正式 policy。Web 服务升级、CRM HTTPS 入口、EXE OTA 三者独立。
- **此前表中四个 EXE 属于核心83aaccd检查点，不含本轮新增 Ed25519/固定HTTPS源代码；保留原字节，不把旧包说成新功能已打包。** 等本轮代码独审及真实 HTTPS 入口就绪后统一最终构建，不逐项重复打包。

### 推荐：pinned-key-ed25519

发行构建固定政策示意（占位不能启用）：

```json
{
  "enabled": true,
  "trust": "pinned-key-ed25519",
  "feedUrl": "https://updates.example.invalid/crm/",
  "keyId": "真实SPKI公钥SHA256前32位十六进制",
  "publicKey": "-----BEGIN PUBLIC KEY-----\n真实Ed25519公钥\n-----END PUBLIC KEY-----\n",
  "minSequence": 1
}
```

公钥仅来自可信人工分发的构建，不从服务器接收新公钥；`keyId` 不是信任替代品，实际固定完整 Ed25519 SPKI 公钥。初次客户端/公钥必须通过已可信的人工渠道分发。正常轮换用当前信任根签署包含新公钥的新客户端，且序号继续单调增加；不能仅让服务器声明一个新 key。如果旧私钥已经泄露，不能再依赖它安全授权轮换，应走新的可信人工分发。

固定 feed 只取 `manifest.json` **原始 UTF-8 字节**（最大16KiB）与 `manifest.sig`（原始64字节 detached签名）。先用客户端固定公钥对原始字节验 Ed25519，成功后才 UTF-8解码、JSON解析、信任字段。签名是对落盘原字节，不是客户端重新序列化的 JSON。

清单仅允许以下确切字段，平台/架构/文件名与版本必须精确绑定：

```json
{
  "format": "philosopher-crm-ota-v1",
  "keyId": "固定公钥的标识",
  "version": "1.0.1",
  "sequence": 1,
  "platform": "win32",
  "arch": "x64",
  "file": "PhilosopherStoneCRM-Setup-1.0.1-x64.exe",
  "size": 121672690,
  "sha256": "64位真实安装包小写SHA256"
}
```

只允许严格稳定版 x.y.z、正安全整数 sequence、固定 basename、完整 per-user x64 EXE、最多512MiB；清单不接受任意 URL、包路径、额外字段、服务器自报密钥或安装命令。大小/摘要均覆盖实际安装器完整字节。策略最低序号与 userData `ota-high-water.json` 防版本/序号回退，同序号不同清单摘要/密钥拒绝。**高水位仅在完整安装包签名绑定+size/hash全部通过后原子提交**，半包、坏包、验签失败或取消下载不推进；同序号相同原清单可合法重试，损坏的高水位拒绝覆盖。

下载用 Node HTTPS，固定 origin 和发布目录、正常证书验证、拒绝所有 HTTP重定向（包括同源）、拒压缩变换、限制响应字节/空闲15秒/总时限300秒。先下载唯一随机 `.part`，核实际size/SHA256后才提升到由sequence+manifestHash+basename命名的受控缓存；失败只清本人该临时文件，不删除用户数据。**不读取或信任未签 latest.yml**。

仍复用锁定 `electron-updater 6.8.11` 的 NSIS安装入口，而不另造更新平台：只有已验清单与包才能 `prepareVerified`，经真实 `getOrCreateDownloadHelper` / `setDownloadedFile` 建立本地安装状态；没有 updater 网络元数据参与该策略。安装需用户“已保存，安装并重启”确认及flush/设置备份成功，然后再次验原清单签名、版本/高水位、缓存实际路径、文件类型、size和SHA256；真实同步 `doInstall` 在spawn之前又复核一遍。没有 `verifyUpdateCodeSignature=false`：未绑定清单的默认签名入口明确抛错，独立 override 只能在验证绑定通过后返回成功。`autoDownload=false`、`autoInstallOnAppQuit=false`、`allowDowngrade=false` 不变。

### 私钥生成、离线签发与备份

**生产私钥尚未生成。** 主控仅认可建议路径 `C:\Users\74090\AppData\Local\PhilosopherStoneCRM-ReleaseKeys`，尚未授权实际创建/写生产密钥。后续单独明确生成后才运行（当前不要执行）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/generate-release-key.ps1 -Directory 'C:\Users\74090\AppData\Local\PhilosopherStoneCRM-ReleaseKeys'
```

脚本只接受明确本机绝对目录，拒绝已有目录/文件与链接祖先；先创建受保护独占ACL（当前用户+SYSTEM，禁止继承）再由Node生成Ed25519。私钥PKCS8 PEM仅写 `private-key.pem`、不stdout、不进参数正文、不写Git/包/服务器；公钥写 `public-key.pem`，`key-id.txt` 保存公开标识。文件继承专用ACL；签发前再次检查所有密钥目录ACL主体/owner。管理员或同一用户被控制不在此边界保证内，私钥PEM本身不是加密备份。

用户应把私钥另存授权的离线加密介质，保留keyId/公钥指纹和已用最高sequence，限制发布机/备份访问；不要放项目、OneDrive或服务器。没有备份丢失私钥只能可信人工重新分发，不能让服务器换钥。此轮实际生成过的仅 `.validation/key-test-*` 的明确测试密钥，测试结束已经清理；不会生成测试policy到生产配置。

离线签发（私钥目录只作为路径，不在命令行传密钥正文）：

```powershell
node scripts/release-tools.cjs sign '<专用安全密钥目录>' '<PhilosopherStoneCRM-Setup-1.0.1-x64.exe的完整路径>' 1.0.1 1 '<全新输出目录>'
```

真实脚本核独占ACL与keyId、读取离线私钥，构造size/SHA256绑定清单并签原始字节，只输出 `manifest.json` / `manifest.sig` 到全新目录，拒覆盖，不输出私钥。先把对应 EXE 不可变上传核摘要，再发布严格配对清单与签名；中途读到不匹配配对只会拒绝并可重试，不提交高水位。不得覆盖旧版本 EXE 为新字节，也不在客户端安装目录存私钥。

### 可选：原 Authenticode 策略

选择 `trust: "authenticode"`（旧配置省略trust仍按该策略）时，确实需要有效公信签名证书、HTTPS feed、完整 `publisherName` Subject 和 `certificateSha256` pin。固定 feed/publisher 只来自发行构建，原严格PowerShell Valid+path+Subject+pin、下载后及安装前SHA512复核保持。updater 6.8.11 的缺 publisher/config/PowerShell能力 fail-open 不会被采用；无证书在**此策略**仍拒绝，不自动变成pinned-key。

`beforePack` 生成 `resources/app-update.yml` 供真实6.8.11缓存初始化；固定 `updaterCacheDirName`。仅Authenticode模式放 provider/url/publisher，pinned-key模式只需缓存名称，不用其 feed 元数据。默认未配置仍不实例化更新器。

两种策略都没有健康自动回滚：坏版本优先发更高版本兼容修复，保留专属profile冷备份。不能用旧Chromium直接读取新profile而承诺安全降级。生产HTTPS签名渠道和真正NSIS OTA安装仍未实际演练；真实密码学/ACL/锁定依赖状态测试不代替GUI、托管或生产密钥交付。

## 覆盖升级与隔离验收步骤

正常升级：保存全部 CRM 表单 → 完全退出客户端 → 核安装包 SHA256/发布者签名 → 同一 Windows 用户运行新版本安装器，保持安装身份/目录 → 启动 → 检查设置与业务操作；安装器只换程序，不清 AppData。备份应在客户端完全退出后复制整个专属 userData（包括 browser），保存在使用者授权目录；本任务不自动读取或备份已有浏览器/客户资料。

GUI 操作者开始前：

```powershell
node scripts/preflight-install.cjs
node scripts/preflight-install.cjs --acceptance
```

此脚本只看相关路径存在性和 HKCU 卸载注册，不读取配置/会话正文；未知数据或安装存在就停报，不覆盖/删除。生产身份初次检查已见 AppData/目标目录/注册均不存在（这是检查时点事实，安装前仍需复核）。

验收变体 package.name 为 `philosopher-stone-crm-acceptance`，固定 `com.philosophersstone.crm.acceptance` / `PhilosopherStoneCRM-Acceptance.exe` / `%APPDATA%\PhilosopherStoneCRM-Acceptance`，仍用 `persist:crm`。两版使用同一生产 main/security/tunnel/settings迁移/updater模块和同一 NSIS 脚本；只更换固定身份后缀、测试显示名/快捷方式、测试入口。`scripts/build-acceptance.cjs` 在 gitignored staging 构建两版；生产白名单不含 fixture/HTTP服务器/验收 IPC，更没有远程调试或任意执行 JS 开关。

1. 用 acceptance **1.0.0** 真 NSIS 安装到专属 `.validation/installed-acceptance`（不提权、不改现有用户/浏览器）。运行验收 EXE，会同时出现真实本地设置与验收页面。
2. 验收页只首次点“写入合成哨兵”：生产 SettingsStore 写测试设置、受控设置 HttpOnly 持久合成 Cookie，页面写 localStorage/IndexedDB。
3. 分别点击 HTTP attachment 和 Blob 中文 CSV 下载。仅测试变体自动保存在专属 `fixture-downloads/合成验收.csv`，不弹生产的下载对话框；内容为固定公开合成字节，不含客户资料。这一自动保存是明确测试差异。
4. 点“验证并保存”，得到 userData 下 `receipt-1.0.0.json`（版本、profile、partition、settingsSHA256、localStorage/IndexedDB合成值、Cookie仅布尔、下载SHA256、Node不可用）。不输出 sid/真实 Cookie。
5. 正常退出两个窗口，确认进程退出，再用 acceptance **1.0.1** 覆盖同目录。冷启动后**不要再写哨兵/下载**，直接点“验证并保存”，逐值比 `receipt-1.0.1.json` 与旧报告；版本应变、profile/partition/设置摘要/下载摘要/两种存储/Cookie应保持。
6. 生产安装器另在 preflight 无冲突时装到 `.validation/installed-production`，正常启动本地设置页、默认 OTA disabled、用已核验外部隧道或个人连接进入标准 CRM 登录；不读旧 Edge 数据、不复用管理员私钥。具体真实 UI/连接结果由授权 GUI 操作者补证。

## Edge / PWA 迁移边界

Electron 的 userData/分区与 Edge profile 独立，**不扫描、不导入、不复制、不清理 Edge 的 Cookie、缓存、Local Storage、IndexedDB、下载或已安装 PWA**。Edge 加密 Cookie 不可直接挪用；新客户端首次正常登录。服务端 CRM 数据仍在同一服务端；旧浏览器未提交草稿/仅本地资料需用户在旧端自行处理，客户端不能承诺自动迁移。旧 PWA 可保留，不自动卸载。

## 已有验证与待验

- 核心 checkpoint `927aa34`：Node 内置测试19项全部通过，含设置保留/迁移/未来与坏配置拒绝、安全 IPC、origin/下载限制、严格SSH参数/忙端口拒绝、OTA disabled、签名状态/Subject/pin/路径拒绝、PowerShell错误/超时/坏输出、SHA/半包/缓存替换/取消/flush失败；真实 Windows PowerShell 对未签文件的拒绝已运行。
- 后续核心 `83aaccd` 修复独审 seq135 两个P2（合法确认外链、真实 updater 缓存配置），新增实际锁定 updater 离线集成，**22/22通过、0跳过**。构建/验收脚本冻结 `44b08d5`，该增量未改核心。
- Electron CLI 实测 `v45.2.3`；官方精确 registry 安装成功。最终品牌四包 NSIS 均 exit0，`inspect-artifacts.cjs` 核版本/独立 package身份/ASAR生产源逐字节/fuse/OTA配置与默认禁用/许可证全部通过。原始 runtime zip 的官方已知 SHA256已重验，未改 fuses 的旧 runtime 不作为输入。构建日志没有默认图标警告，保留 Electron/Chromium 许可证。真实 Windows Authenticode 查询四安装器均为 `NotSigned`（枚举2），不宣称已签名。
- 最终打包过程中 acceptance 的相对 beforePack hook 被 builder 的工作区边界守卫拒绝；将生成配置指向 **stage 内复制脚本的绝对路径** 后，欠的两包成功。没有放宽边界守卫或重写打包器。标准 GitHub超时与该次拒绝均保留，不用后继成功抹去历史。

### 最终工件（当前源码核心83aaccd / 构建脚本44b08d5）

根目录 `deploy/windows/desktop/`；这些工件 gitignored，仅本机交付，不提交安装器。

| 工件 | 字节 | SHA256 |
|---|---:|---|
| `dist/PhilosopherStoneCRM-Setup-1.0.0-x64.exe` | 121672488 | `bbab9b31d5e71fd6cafb81e9ee21986f4a80fee163e03f6f48047ec9c7ab0e30` |
| `dist-next/PhilosopherStoneCRM-Setup-1.0.1-x64.exe` | 121672690 | `5a417df1881a55c84a580512d567cd0a7c309f3e16e9d9b1ea8dcb1cf74fffdf` |
| `.validation/acceptance-1.0.0/PhilosopherStoneCRM-Acceptance-Setup-1.0.0-x64.exe` | 121672171 | `6cbd6f462204f5bd6266945870c638104b3678bc9ea0ddf4468f4740469cc10e` |
| `.validation/acceptance-1.0.1/PhilosopherStoneCRM-Acceptance-Setup-1.0.1-x64.exe` | 121672110 | `ef14376a78895482a3b62f80509988780adc56954ebf3091c04f8c1e8cfbadac` |

完整 ASAR/EXE/安装器摘要、源字节比较集合、fuse 值与版本在 gitignored `.validation/artifact-inspection.json`；可用 `node scripts/inspect-artifacts.cjs` 重算。实际两版操作后用 `node scripts/compare-acceptance.cjs` 只读比较合成两报告，要求 N 实际下载两次、N+1 不重新下载/重 seed。未签安装器可能触发 Windows 来源/SmartScreen 警告，不应关闭系统安全保护。

### 实际 GUI 阻碍与最短续作

Terra 已加载当前 Windows 桌面技能并完整读取 API reference，但此 worker 和主控会话都缺必需的 `js` / `js_reset` 工具，**没有启动任何安装器、没有写哨兵、没有覆盖升级或登录**。Terra 独立确认 production/acceptance preflight 都为 `safeForFreshInstall=true`，并复核三份交接安装包 SHA256 一致；这是检查时点事实，不是安装或数据保留成功。主控明确暂停实际 GUI，不用 shell 静默安装、模拟点击、内置浏览器、新系统用户或提权绕过工具边界。

在具备 Windows 桌面工具的新会话/重载会话中接续（不需重构建）：

1. 进入 `P:\CRM\.tower\worktrees\wt-41\deploy\windows\desktop`；按上表核三份将使用安装器的 SHA256，再运行两种 preflight。出现未知路径/注册就停止，不删除/覆盖。
2. 在真实 Windows GUI 打开 `.validation/acceptance-1.0.0/PhilosopherStoneCRM-Acceptance-Setup-1.0.0-x64.exe`，按前节六步完成专属安装、首次写哨兵、HTTP/Blob下载、保存N报告、正常退出、N+1覆盖与冷启动只验证。
3. 执行 `node scripts/compare-acceptance.cjs`，应 PASS，检查两版本设置摘要/固定profile/partition/localStorage/IndexedDB/持久合成Cookie/下载摘要全部保持。未生成两份真实报告前，此脚本无法也不应通过。
4. production preflight仍无冲突才用 `dist/PhilosopherStoneCRM-Setup-1.0.0-x64.exe` 真GUI装到专属 `.validation/installed-production`，启动设置、核OTA disabled，正常连接已核验外部隧道18088→标准CRM登录，不读Edge会话/不借管理员私钥。
5. 将 GUI 观察与合成两报告回传主控，补本页证据，任务2/4再勾选。当前任务仍未Complete，实际启动与覆盖保留未验。

上述“不需重构建”仅指既有核心83aaccd检查点旧包的GUI续作。**本轮新Ed25519和HTTPS入口代码必须等审定/入口就绪后统一构建新包再验，不能用旧包认证新能力。** 生产应用签名密钥、公钥固定和HTTPS OTA托管尚未配置；Windows公信代码签名不是应用签名策略的必要前置。普通技术实现无需新增用户价值取舍，实际GUI仍受工具可用性阻碍。

## 直连现有服务器的最新方向

用户最新明确要求直接连接 `8.133.190.46`，不把本地SSH中转作为最终产品UX。M17正在核安全HTTPS入口条件，目前**尚无经证据验证可用的HTTPS真实IP/域名地址**。因此当前 `release/connection-policy.json` 为 `{"enabled":false}`，不猜 `https://8.133.190.46`、不改成公网HTTP、不忽略证书错误、不传播或打包dev管理私钥。旧严格SSH选项仅作兼容，不继续扩张为新默认流程。

就绪并经主控确认实际TLS入口后，发行构建可固定单独的CRM连接政策（与OTA feed/policy完全不同）：

```json
{
  "enabled": true,
  "httpsOrigin": "https://实际经核验的入口"
}
```

`beforePack` 验证其为无路径/凭据的HTTPS origin。仅当 `settings.json` 尚不存在时，客户端把该发行政策初始化成可信HTTPS默认连接；已有设置、旧origin与Cookie/缓存不覆盖、不迁移、不清理。已有用户应在设置中明确选择新入口、核验并保存后重新登录；原服务端数据仍在同一服务端数据库，不能把origin切换说成数据迁移。新设置或已明确保存的HTTPS连接启动时自动健康检查并打开标准登录，失败返回本地设置、拒绝降级TLS。

此轮没有创建任何用户本机连接配置、没有读取SSH私钥正文或旧浏览器资料、没有向服务器开放8088或修改公网入口。已请求M17停止为客户端传播管理员机器路径；最终真实HTTPS默认值等M17与主控证据后再填。

本轮定向验证：`npm test` **37/37 PASS、0跳过**；包含真实 Ed25519原字节正负例、错误key/签名/包替换、版本/序号回退、半包网络失败后合法重试、用户取消/flush失败、真实锁定NsisUpdater缓存准备与同步安装守卫（spawn仅spy，未执行任何未知包）、测试专用ACL密钥生成和真实离线签发CLI、HTTPS新profile初始化/旧origin不覆盖。`node --check` 全部JS/CJS、默认配置 `prepare-release` 和 `git diff --check` 通过。无生产密钥生成、无公网发布/SSH操作、无新包构建或GUI安装；这些边界未用测试结果替代。

### seq137 定点修复：损坏缓存的合法恢复

Sol seq137 对 `7001e8e` 指出唯一P2：已下载缓存损坏后虽然安装正确拒绝，但原 `existsSync` 令同一签名发布在同实例或重启后始终跳过重新下载。现改为先验证受控缓存；仅普通单链接文件的**大小/摘要不符**允许完整重新获取，仍先验原清单及高水位。新随机 `.part` 必须通过普通文件/实际size/SHA256校验，再复核目标缓存仍是受控普通文件后原子替换；下载/验包失败保留原坏缓存和高水位，清理仅本人该随机临时文件。链接、目录、路径变化、权限/I/O、签名或高水位错误不作为可恢复坏包吞掉；不会递归清用户目录或删高水位。安装前及真实NSIS同步入口的再次验签/实际文件校验保持。

定向测试命令：`node --test --test-name-pattern='damaged ordinary cache|failed replacement|cache recovery rejects|post-download package substitution|real locked NsisUpdater|high-water rejects' deploy/windows/desktop/test/pinned-update.test.cjs`，**6/6 PASS、0跳过**。新增覆盖同实例同长度坏包/新控制器重启后截断包的同序号原清单重试，确认真实重新下载、恢复ready后才可安装；下载中断/新包hash错误不替换原文件、不改高水位；已有硬链接/目录及下载间目标换链接全部拒绝，不触无关哨兵。原坏包拒安装、回退与真实锁定NSIS同步守卫亦定向通过。仅重跑受影响范围，未重复旧GUI/密钥/网络矩阵。生产key/feed/HTTPS配置和旧四EXE字节均未改变，未重包、未生成生产私钥；GUI工具block仍保留。
