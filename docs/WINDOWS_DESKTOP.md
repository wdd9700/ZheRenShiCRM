# 哲人石CRM Windows 桌面客户端 W020

## 状态与决策

2026-11-08：已实现安全薄壳、持久设置、严格 SSH 与默认关闭的 OTA，已实际构建两版 x64 NSIS 安装器。**GUI 安装、覆盖升级与真实 CRM 连接正在交接验证，尚不能称为已验收。当前没有生产签名证书或 OTA 托管，产物未签名，不是生产 OTA 已就绪。** 最终产物摘要与 GUI 证据在本页末尾补充；早期默认 Electron 图标包只是阶段产物。

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

## OTA：能力、配置与明确未就绪项

当前 `release/ota-policy.json` 为 `{"enabled":false}`；UI 显示“OTA 未配置，已禁用”，不自动检查、下载或安装。Web 服务端更新与客户端 EXE OTA 是两个独立流程。

只有发行管理员准备好有效 Authenticode 公信签名证书、HTTPS 托管及发布授权后，才可在**构建源**中修改策略并重新构建：

```json
{
  "enabled": true,
  "feedUrl": "https://updates.example.invalid/crm/",
  "publisherName": "CN=完整真实发布者, O=真实组织",
  "certificateSha256": ["64位真实签名证书DER的SHA256十六进制摘要"]
}
```

`beforePack` 每次从同一策略生成并打包 `resources/app-update.yml`（JSON 格式是合法 YAML），包含固定 `updaterCacheDirName: philosopher-stone-crm-updater`，启用时也包含一致的 feed/publisher。此文件是 updater 6.8.11 下载缓存初始化的实际必需输入，不可只传构造器 URL 就省略；默认 disabled 仍不实例化 updater。真实锁定依赖的离线缓存初始化与严格验签调用已有定向测试。

以上是占位示例，不是可用渠道。完整证书 Subject 精确匹配；证书轮换须预先审定 pin 列表。发布源仅固定 HTTPS 同 origin 且同目录，元数据/文件/重定向均受限；不允许页面/普通设置改 feed/publisher，不打包 PFX、密码、发布 token。固定 latest/stable、x64、完整单 EXE，不支持 web installer、预发布、降级或跨发布站跳转。

**避免 updater 6.8.11 的默认 fail-open：** 该版本缺 `publisherName`/`app-update.yml` 时可跳过验签，默认 PowerShell verifier 某些能力异常也会放行。本实现继承 `NsisUpdater` 强制调用自定义严格 verifier，而非依赖磁盘配置是否有 publisher。验证用固定系统绝对路径 WindowsPowerShell、`execFile`/`shell:false`、EncodedCommand + LiteralPath；仅当 `Get-AuthenticodeSignature` 状态为 **Valid**、返回被验路径相等、完整 Subject 和证书 SHA256 pin 匹配才通过。启动失败、超时、stderr、JSON/缺字段/身份/签名不符一律拒绝。不自签冒充公信，不以 SHA512 代替签名。

`autoDownload=false`、`autoInstallOnAppQuit=false`、`allowDowngrade=false`。用户先检查、明确确认下载；完整下载检查大小、SHA512、签名与验签前后文件哈希。安装另需原生“已保存，安装并重启”确认；先 flush/备份成功，再重验签名+SHA512/缓存路径，最终同步安装入口还检查路径/哈希。出错保留旧版，不自动安装。HTTPS/TLS 真实渠道、受信签名完整成功链尚未测试；受控负例和真实本机未签文件拒绝不等同生产 OTA 演练。

发布时先不可变上传签名 EXE + blockmap 并核大小/摘要，再原子发布 latest.yml（包含准确 version、files.url/sha512/size）；单调提高版本。不能让旧版本元数据引用被覆盖的新字节。保留旧已签安装器及客户端冷备份，但 **NSIS/updater 不提供健康自动回滚**：坏版本优先发更高版本的兼容修复；只有单独验证兼容的冷快照/程序配对才人工回退，不用旧 Chromium 直接打开新版 profile。

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
- GUI 真安装、两版实际覆盖存储保留、标准 CRM 连接与生产身份最小启动仍待授权操作者结果；不把受控测试或构建通过说成安装通过。真实证书/托管/受信 OTA 成功链未有，不伪称已上线。
