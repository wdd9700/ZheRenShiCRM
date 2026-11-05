# D020100 Safe Tab Resume — 候选实现与验收门槛

状态：代码/测试契约与固定源重放已完成；telemetry 代码审查结论保留，1c586261 原字节完整 SFC 已通过，主控确认 8c5 / 2c695eb2 构建通过。**原生浏览器真实 hidden→visible 尚未触发并验收，整体交付门仍未关闭。**

## 起点与决策

- foundation `36521b0`，未 revert/amend/merge/cherry-pick。M20 已审 `87386bc8493b9e0605224adfdcf3aacd42595d6f` 的初始化诊断、允许值列表、first-failure 与 DEV Promise 错误链作为前置保留，归属 M20。
- D020100（Provisional）：采用明确页面/草稿适配器、新 Vue/Pinia/socket 运行域与模块缓存隔离。不遍历资源 reload、不自动重放写请求、不做通用 Vue 快照、不仅凭同 user 揭罩。
- 恢复顺序：先遮罩 → 捕获允许的同标签内存草稿 → 旧 epoch 失效/停止运行域 → 服务端身份 → 当前页面 fresh read/create 权限 → fresh 只读请求和新域挂载 → mounted 页面/详情活动区登记 → 等待读请求与 Vue 更新达到稳定修订号 → 第二次服务端身份和 epoch 复核 → 揭罩。恢复最多 15 秒，失败遮罩且可显式重试；再次 hidden 使旧恢复失效。
- 初始 hidden 也执行带超时的 no-store 服务端身份握手，但不挂载/不揭罩/不允许业务请求；成功进入 `BOOT_WAIT_VISIBLE`，显示“服务端身份已确认；当前标签在后台，业务读取仍暂停”。真正 visible 后重新核验身份才初始化；若握手进行中变 visible，同样补第二次身份核验。后台单独 focus 不假装可见，不重复请求；真实已 visible 的 focus 可唤起等待。后台失败保留明确允许值诊断及重试，Guest/账号/cookie/广播变化仍终锁；BFCache/epoch 使旧握手不能提交。

### 初始后台握手修复与合并基线

经授权将 M24 rebase 到 master `efff5469744a0808679e3edf8b3e44fad1337c84`，逐冲突保留 M20 诊断和 M24 恢复实现；rebase 后、修复前 `ffd0b26` 的 production payload/source_edits/manifest 与原 `1e01550` 完全相同。合并测试保留 M20 no-store、DEV socket、cookie 和诊断值允许列表断言；旧“hidden 永久终锁”期望由 M24 恢复契约替代。

主控真实证据是部分导航链停在原始 `IDENTITY/NONE/NONE`，同样后台真实点击活动页 `/crm` 链接却可建 Lead；因此不能归因为所有后台都失败，也不能把 `panelVisible=false` 等同已测 document.hidden。源码握手不读取 pathname，`/crm` 与 `/crm/` 的真实重定向/加载生命周期差异仍需 M9 与正常 browser 定向复验，不能靠路径特判修复。此修复只消除“实际初始 hidden 时连身份握手都不开始”的确定代码路径，不声称已证明它是所有挂起的唯一根因。后台业务仍暂停是明确安全行为，不要求用户盯面板才能完成身份确认。

本轮本地四 suite 50/50 pass；新增实际 boundary/main 回归覆盖后台身份成功但 ready 不解锁/零 mount/零插件、业务读写拒绝、真实 visible/focus 后再验、握手中 visible、后台 Guest/HTTP/redirect/响应错误/离线/超时及重试、账号/cookie/广播变化、BFCache 旧响应与单 flight。运行环境未触碰；新 tip 标准构建/native/bridge 和正常 UI 验收由 M9 独占，待独审后进行。

## 支持边界

支持桌面 `Leads` / `Deals` 当前列表参数（含筛选、排序、分页参数）、`Lead` / `Deal` 详情（**包括默认 #activity**，不是仅 #data），以及列表内 Lead/Deal 创建表单。详情等待实际 Activities mounted 标记与活动请求；恢复期禁自动 markVisited 和 onboarding 写操作。只读端点逐项允许，任意其他请求会使本次 hydration 失败，不能用 GET 伪装写入。

草稿仅保留当前标签内存中的可见、可写、permlevel 0 标量字段差异，既有记录与创建表单分开。重新读取文档、字段 meta、read/write/create 权限后显示无值提示，由用户明确“恢复未提交编辑（不保存）”；恢复前再查当前权限。服务端值不同于基线及草稿值时报告冲突，不覆盖、不自动提交。撤销的字段/写权限对应草稿被丢弃，恢复权限也不会重新显示旧差异。

复杂邮件/Comment/Note/Task 编辑器、Table/附件/未知字段差异、其他页面或 dialog 没有自动草稿适配器：检测到后保持业务遮罩和原标签内存，明确提示不支持，并提供“放弃未保存编辑并刷新”、标准登录和退出登录安全路径。不会因普通只读 #activity 默认页面而一概卡死。移动详情尚未增加 mounted 适配器，不宣称支持。浏览器关闭/刷新会丢失内存草稿；不保存到 localStorage/IndexedDB、不广播、不上传草稿。

客户端检查无法替代服务端最终授权/CSRF，也不能保证两次身份请求之间远端权限原子不变；最终读写授权仍由服务端负责。失败关闭策略是降低暴露风险，不是新的服务端安全边界。

## 隔离与契约

- generic/list/document resource 捕获 epoch；旧读成功、错误、异步校验、写回调不进入新域。缓存 key 含 scope/epoch；保留同步发布 `resource.promise` 和被忽略 auto rejection 的处理契约。
- 旧 Vue app unmount、Pinia dispose/state 清空、socket 去监听并断开；document/meta/script/controller/assignee/permission 缓存及弹窗/通知/设置/通信开关等模块引用显式清理。旧 users/views store 的数据集合也清空，旧定时背景请求不会跨 epoch 发出。
- 恢复时不运行表单 onLoad/onRender 自动脚本；首次明确用户交互再初始化控制器（不重放这些生命周期）。未知恢复请求 poison 屏障，即使组件吞掉错误也不会揭罩。
- M20 的 C011100 诊断只保留固定 stage/failure 值，不记录 cookie、用户名、原异常/堆栈。

## 补丁与固定证据

`frontend-patches/c011000/manifest.json` 当前包含 **38 个修改目标（9 payload + 29 strict source edits）及 5 个只读 guard**。`apply.py` 仍要求真实 CRM HEAD `36bd8859f2a6345a620477bc708d0546e8c3f08a` 和每个 before SHA 完全匹配；所有目标检查完成才写。source edits 每个 anchor 必须唯一，输出 after SHA 同样校验；拒绝漂移、缺文件、重复应用、链接目标与已有临时文件。此补丁面向固定未 patch 源，不可直接覆盖 M19/M20 已 patch 运行目录。

只读使用两份本地证据，不修改它们：

1. `P:/CRM/.tower/worktrees/wt-17/deploy/.runtime/m19-fixed-frontend-evidence`：原 7 payload 的未 patch baseline 与 guard。
2. `P:/CRM/.tower/worktrees/wt-9/deploy/.runtime/m20-public-frontend-evidence-3828e3eb572143f99e2420809fd5f1b2/apps/crm`：新增 strict source 和已有 Vue 3.5.32 / Pinia 2.3.1 / Babel parser。

`check_apply.py` 可将两份证据中 before SHA 精确匹配的文件复制到私有可删除 fixture。**fixture 的 Git HEAD 是 unittest mock，仅验证严格重放，不是冒充真实 Git checkout 或构建。**

## 本地验证与复现

在 wt-24，Git Bash：

```bash
C011100_FRONTEND_ROOT='P:/CRM/.tower/worktrees/wt-9/deploy/.runtime/m20-public-frontend-evidence-3828e3eb572143f99e2420809fd5f1b2/apps/crm/frontend' \
node --experimental-vm-modules --test frontend-patches/c011000/controlled.test.mjs frontend-patches/c011000/initialization.test.mjs frontend-patches/c011000/resume.test.mjs frontend-patches/c011000/real-runtime.test.mjs

PYTHONDONTWRITEBYTECODE=1 python frontend-patches/c011000/check_apply.py \
P:/CRM/.tower/worktrees/wt-17/deploy/.runtime/m19-fixed-frontend-evidence \
frontend-patches/c011000 \
P:/CRM/.tower/worktrees/wt-9/deploy/.runtime/m20-public-frontend-evidence-3828e3eb572143f99e2420809fd5f1b2/apps/crm
```

结果：41 tests / 41 pass / 0 fail；36 目标严格重放通过，dry-run 无写；漂移/缺文件/错误 HEAD/hardlink/已有临时文件/重复应用拒绝且零写。原 18 个资源/Promise/默认视图/深链回归保留。新增覆盖初始化诊断、初始 hidden、重复恢复/再次 hidden、旧请求与写不重放、账号/Guest/广播/cookie、BFCache、网络重试、草稿权限/创建权限/冲突。

真实运行测试使用真实 Vue renderer/Pinia，实际执行 payload main/session/boundary/resources/resumeRuntime/safeResume，以及固定上游经过 strict transform 的 useDocument/meta；同时用固定 Babel parser 解析所有改动 JS/TS/JSX 和 Vue script。它使用合成业务响应、插件/路由替身及小型测试组件，**没有编译完整 CRM SFC、没有真实 vue-router 导航，也不是浏览器端到端测试**。测试中相同替身 plugin 的重复安装警告不是生产组件证据。Vitest bridge 已接入全部四个 suite，但本机无 vitest，未运行 bridge 本身。

## R1 两项 P1 回修与 bridge 修复

- `CommunicationArea` 的 email/comment/signature/attachments 原 `useStorage` 路径全部改为组件内存 ref，不读写也不删除旧持久 key；`communicationEditorHeight` 非敏感偏好保持。收起的邮箱/评论/附件及收件人/主题变化由显式 registry 识别，capture 同时检查所有 contenteditable，不只第一个。未支持编辑器重试/再次 hidden 不销毁原内存；身份/Guest/权限拒绝或显式丢弃会清除内存，新挂载/刷新不会读回旧持久草稿。旧 key 仍留在浏览器，不宣称已安全擦除；回滚到旧版可能重新读取，回滚须另行决定这四类业务 key 的定向迁移/清理，不能无差别删存储。
- 新增 `crm.api.get_unsubscribed_emails` 恢复期只读允许项前核了固定 commit 的 [服务端函数](https://raw.githubusercontent.com/frappe/crm/36bd8859f2a6345a620477bc708d0546e8c3f08a/crm/api/__init__.py)：先 `frappe.has_permission(doctype, "read", name, throw=True)`，随后只 select Email Unsubscribe，无写操作。测试实际执行转换后的 CommunicationArea setup 与固定 EmailEditor immediate recipient watcher，带非空 email、合成 unsubscribe 列表响应走恢复链；仍不是对真实 HTTP 服务的实测。
- 新增 3 组真实运行回归：默认活动非空 email 正常恢复；收起邮件/评论/附件检测，账号/Guest/撤权清内存、重新挂载不访问旧 key；多 contenteditable 和明确丢弃。原 unsupported 编辑器连续 hide 也有独立回归。
- real-runtime source loader 默认严格接受每个 manifest before 或 after SHA：before 转换并复核 after；after 原字节执行；其余 drift 拒绝。因此 bridge 可运行已 patch cwd，不会重复套 source edit。`C011100_SOURCE_ROOT` 可分离只读源码证据，`C011100_FRONTEND_ROOT` 只为既有依赖定位；`check_apply` 在设置后者时自动再以重放后的 after fixture 运行真实测试。生产 apply 的 before 门槛没有放宽。Python 默认 Windows `python`、Linux `python3`，可 `C011100_PYTHON` 指定。

## 已审导航叠加的测试采证契约

最终组合的四 suite 子进程曾真实 exit 1，原因是 Sidebar 已合法叠加导航，而旧 loader 仅接受 M24 before/after，并非 Vue/Pinia 行为失败。测试专用 `runtime_sources.py` 额外仅接受已审 `l3-scheduling@4ff499e` 的 Sidebar after `e169f9d13cec9245390a8854b1dba8026227945abcaac03fb097473fca29a852`。随测试保存该 commit 的原始 manifest，SHA256 固定为 `74787afa31373457e9b91fa8ea6f53e4e3317854670656558579df0762b75670`；核 manifest overlap 与 M24 before/after 一致，逆序撤回其中恰好三处唯一 replacement 后，必须还原 M24 after SHA，且保留 accountBoundary import/HYDRATING 守卫。返回并解析的仍是实际组合源码，不替换为旧 Sidebar。未知 hash、manifest/变换/守卫漂移均拒绝，其余文件仍保持精确 before/after；生产 apply/payload 未改。

该轮本地四 suite 46/46 pass，新增回归覆盖原 before/after、合法组合及 manifest、overlap、守卫、所有目标未知字节拒绝。M9 当时最终组合 native 已采证 exit 0、34 files / 326 tests pass、无 Vitest-reported unhandled；stderr 仍有 2 AbortError、16 ECONNREFUSED。实际 happy-dom Fetch.onError 会先 console.error 再 reject，Vitest teardown 调用 happyDOM.abort 会 destroy(error)，这与报告未消费 Promise 的语义不同；连接拒绝逐条 URL 不能仅由 Node 栈归因，不能宣称 stderr 全无错误。后续 `951a4b9` 也已由 M9 标准 build/native/bridge 通过，但这些历史证据不覆盖下面的新生产修改。

## 创建表单恢复竞态的因果复现与回修

正常 Windows tab 往返实测中，同身份 Lead 创建表单未保存字段进入通用恢复失败，显式重试仍失败；原诊断 `C011100 / READY / READY / PAGE_HIDDEN` 是历史 first-failure，不能定位本次失败阶段。现场网络身份、权限和已完成业务请求均成功；没有足够证据将唯一挂起 socket 认定为原因，也没有证明现场失败恰好来自下面这一条竞态。

先在未修生产源码上扩展既有 real-runtime 测试，执行固定 LeadModal 完整 script setup、实际 statusesStore、Vue 3.5.32 / Pinia 2.3.1、补丁 useDocument/resources/main。首次成功后设置未保存 first_name，真实 boundary hide/show，仅延迟新 statuses 的 get_list 成功返回，让 layout 先完成：定向测试 exit 1，恢复进入 `RETRY_COVERED`，layout transform 的 `getLeadStatus` 稳定抛出 `TypeError: Cannot read properties of null (reading '0')`。新 Pinia 的 `leadStatuses.data` 此时仍为 null。扩展 Deal setup 又复现 mounted hook 读取空 `dealStatuses.value[0].value` 的错误。测试模板、路由及业务响应仍是替身，未声称完整 SFC 或现场唯一根因已证。

Lead/Deal modal 的 QuickEntry layout 改为在对应 status resource 的 `list.fetched` 后由组件作用域 watcher 启动，避免跨资源自动请求竞态；status prefix 对空列表防护，Deal 初始默认值也使用空元素防护。watcher 随组件卸载停止；状态失败仍由原读屏障失败关闭。未新增请求允许项、未改草稿白名单、未自动保存或刷新丢草稿，也未弱化当前权限/身份/epoch 门槛。

新增 D020100 安全恢复诊断，DOM 属性为 `data-crm-resume-stage` / `data-crm-resume-failure`，遮罩同时显示固定枚举；阶段仅 `NONE / IDENTITY / ADAPTER / PERMISSION / FRESH_READ / HYDRATE / BOOT / ROUTER / PAGE_MOUNT / READ_SETTLE / ROUTE_CHECK / COMMIT_IDENTITY / COMMIT / READY`，错误仅 `NONE / TIMEOUT / READ_FAILED / IDENTITY_FAILED / UNSUPPORTED_PAGE / LOCAL_FAILURE`。不输出原异常、堆栈、URL、用户名、文档名或草稿；未知 phase 被忽略，旧 epoch 不能更新诊断，显式重试重新计类，C011100 first-failure 仍保留。timeout 分类测试使用固定 code 的合成异常，不冒充真实等待 15 秒超时实测。

独审对 `ff2c58f` 提出 P2-1：身份复核成功后，实际 unsupported adapter 在 permission phase 前抛错，被旧 `IDENTITY` 阶段误归为 `IDENTITY_FAILED`。先扩展实际 boundary + createResumeAdapter 的既有 unsupported 测试，修前定向 exit 1（实际阶段 `IDENTITY`，期望 `ADAPTER`）。最小回修是在身份成功后的 adapter 调用前记录固定 `ADAPTER` 阶段，catch 分类顺序和安全控制不变。回归同时验证身份成功得到 `UNSUPPORTED_PAGE`、unsupported 标记仍存在时真实身份请求拒绝仍得到 `IDENTITY_FAILED`、再次成功恢复正确类别、重复 hidden 及终锁隔离；既有迟到旧 epoch 诊断断言保留。回修后四 suite 54/54 pass，38 修改 + 5 guard 严格重放及 after fixture 14/14 pass。此增量只改 boundary、manifest 精确 hash、既有 resume 测试与本文；未改 modal 修复、权限、草稿或写请求，仍需精确新 tip 独审及 M9 构建。

本轮四 suite **54/54 pass、0 fail**；新增覆盖 Lead/Deal 两种响应顺序、合法空列表、statuses 失败继续遮罩并保留草稿、成功显式恢复而无写请求、换身份不恢复、诊断拒绝任意字符串及旧 epoch、失败分类及重试清理。既有权限撤销、unsupported、通知 Promise、导航 guard 和初始后台握手回归仍通过。严格重放 **38 修改目标 + 5 guard** 通过；after fixture real-runtime **14/14 pass**。Vue 重复安装替身 plugin 警告仍存在，不是完整 SFC 运行证据。

此轮新 tip 必须重新独审，并由 M9 在全新 context/独立 manifest 中标准 build/native/bridge；旧 41 entries 采证须更新为 43 entries，新增 LeadModal/DealModal 严格目标。正常 UI 同身份创建草稿往返及显式恢复仍待下个授权窗口，不以刷新后空表单冒充通过。

## da2177 正常 UI 再失败后的未修生产 SFC 采证候选

主控反馈 `da2177` 标准 build/native 326/bridge 均绿，但真实 Lead 创建草稿切标签及一次显式重试仍为 `READ_SETTLE / READ_FAILED`；54 个已完成业务请求均 HTTP 200，常规 console 只有 socket/扩展噪声。该事实不被局部测试通过覆盖，M24 继续未完成。`hydrationError` 既接收恢复期未声明请求，也接收整个 resource/frappeRequest Promise 拒绝，包含成功 HTTP 后的同步 transform/callback、解析异常和同 epoch superseded；READ_SETTLE 只是最终抛出错误的阶段，不表示第一错误始于这里。auto catch 和边界 catch 可消费异常，因此无 console 业务栈不等于没有本地失败。

只读源码发现一条具体候选路径：`useDocument` 每次调用实际 `getScript`；后者以不存在的 list resource 顶层 `scripts.loading` 判断进行中读取，合法空脚本列表又不创建 `doctypeScripts[doctype]`。FieldLayout/字段再次调用 useDocument 时可能重复 fetch。一次无写入内存实验执行固定 `getScript` 完整函数和实际补丁 boundary/resources/listResource，延迟两次合成成功空列表：两响应均成功，却得到 `RETRY_COVERED / READ_SETTLE / READ_FAILED`，随后进程还以未消费 `Resource request superseded` AbortError exit 1。随后以 runtime_sources 严格 SHA 校验后的 da2177 after getScript 完整函数重复实验，进程级仅收集未消费拒绝类别，断言两次成功响应、同样恢复失败及一个 AbortError 全通过，exit 0；不执行 setupScript，也不编译 SFC，未证明现场唯一根因。生产尚未修改。原 real-runtime 将 getScript 替换成 controllers stub，且只渲染 p，漏掉此真实脚本/模板链，也未执行实际 frappeRequest 转换。

新增 `frontend-patches/c011000/sfc-resume.test.mjs` 是**待 M9 执行的测试候选，不是已通过证据**。它 import 实际 main/App/router，完整挂载 App 的桌面布局、AppSidebar、GlobalModals、Leads、ViewControls/Filter/SortBy/ColumnSettings、LeadModal/Dialog/FieldLayout 和实际字段控件；不替换业务组件、store 或 router.ready。仅 socket.io 外部传输受控且不发送自动事件；fetch 明确列出已读 API 返回结构，未知 method/doctype 立即失败，不兜底成功。脚本列表明确为空。测试内观察 boundary.track 但始终调用原方法，仅保存固定错误类别、源码位置和合成请求顺序；不改产品 runtime。真实 DOM 点 Create、填 First Name、受控 visibility 往返、失败时一次 retry、显式草稿恢复和零写请求均有断言。受控 hidden 只用于单测，不代替 Windows 真实 UI。最初沿用标准 vitest.config 的 framework/icon alias stub；后续静态复核已识别 framework 不能作为空模块边界，独立配置修订见下。

M9 已执行 `976d220` 的单测试，run `10d7ff3463234481bfc30d9465be82d2` exit 1，源码 before/after 守卫均通过。失败在编译：`dialogs.jsx` 转换产物导入 `react/jsx-dev-runtime`，尚未到达 App 挂载或恢复业务。固定正式 `vite.config.js` 第 3/13 行已有 `@vitejs/plugin-vue-jsx` / `vueJsx()`，而 `vitest.config.js` plugins 仅 `vue()`；package.json dependencies 已声明 `@vitejs/plugin-vue-jsx: ^5.1.6`，yarn.lock 第 2411 行锁定 5.1.6，其依赖 Vue Babel JSX 2.0.1。因此是测试缺少正式 Vue JSX 变换，不应安装 React 或 mock dialogs 绕过。

新增独立 `frontend-patches/c011000/vitest.sfc.config.mjs`：导入原 vitest.config 对象，按正式插件顺序在 vue 后追加既有 `vueJsx()`。M9 随后执行 `1259a2a`，run `a43eff14de014e2492510a558f916cdd` exit 1、1 test fail、0 unhandled，JSX 编译障碍已过；首错是 `SFC_FIXTURE_UNDECLARED_REQUEST:crm.www.crm.get_context_for_dev`，随后初始 App 挂载超时和 `DEV_CONTEXT / CONTEXT_EXCEPTION`，没有进入目标恢复业务。后续 AbortError/superseded 不能替代这条首错。生产 source guards 前后均通过。

按固定后端 [crm/www/crm.py](https://raw.githubusercontent.com/frappe/crm/36bd8859f2a6345a620477bc708d0546e8c3f08a/crm/www/crm.py) 的 `get_context_for_dev → get_boot` 返回结构，测试明确补齐版本、站点、CSRF 合成值、sysdefaults、setup、翻译、timezone、state_options 和 demo/FC 标记；不读取真实身份或凭据。静态核对实际 users/views/organizations/notifications/settings/availability/meta/list/layout/telephony 消费结构，保留逐项枚举响应与未知请求失败，不给任意 API 兜底。

静态复核还发现标准 vitest 配置把 `@framework/ui` 指向空 export stub，真实 main 的 telemetry plugin 和 AppSidebar 的 onboarding 不会成立。独立 SFC 配置因此仅将该 alias 替换为正式 vite 的 `../../frappe/ui/src`，并复用其 peer dedupe 列表；保留原 test 设置和 icon stub，不 mock framework 业务组件，不引入生产 PWA 插件。不覆盖正式 vite/vitest 配置，不改依赖或生产 manifest/apply。M9 随后从精确 `sha256:936623e8110ae259dc06032d2750dc122c70a3597e978f7b1e673e95bca5f222` 只读导出 framework ui/src（341 files，manifest SHA `738a359b6ba7abe86dc332eda03dbe2dad2b702d3d67c5b29b57637450ea7807`）。`bc90ed8` 未运行：静态核明确补齐三项启动契约后再交单 case，不宣称回归通过。

真实 `utils/session.ts` 只从 cookie `user_id` 读身份，测试因此在 import main 前设与合成 identity 一致的 cookie，cleanup 定向移除；不是浏览器或生产会话操作。真实 `telemetry/pulse.ts` 的 `BootConfig` 可选字段契约用于精确 `frappe.utils.telemetry.pulse.client.boot_config` 响应 `{ enabled: false, site: 'synthetic.invalid', user: identity }`；不提供真实 host/key，不 mock telemetry 模块。插件仍尝试加载 canonical Pulse client，失败由真实 loader 降级，不把禁用响应夸成跳过模块加载。

真实 `Onboarding/onboarding.ts` 初始 `frappe.onboarding.get_onboarding_status` 返回 `Record<string, StoredStep[]>`，明确提供 `frappecrm_onboarding_status` 五项已完成清单，保留 Sales User 角色及真实组件/store。`setUp` 只赋值/sync 不写；CRM `reconcileOnboarding` 对已完成清单直接返回，空存储也直接返回；`flushPendingSteps` 在本 case 未创建/保存记录时为空，LeadModal 的 completeStep 仅在 insert 成功后调用。故此场景不应发生 onboarding 写；没有给 update API 成功 fixture，并在原零 insert/set_value 断言中加入 `frappe.onboarding.update_user_onboarding_status`。TrialBanner/SignupBanner 在已有 `is_fc_site:false` / `is_demo_site:false` 下不实例化，不盲补 current_site_info 或外部请求。新解析配置与这些 fixture 尚待 M9 单 case 验证，不能声称完整 SFC 或恢复已通过。

M9 真实执行 `13c698e`，run `02f6dc3f7cb84ddc989c1ed81dce8f78` exit 1 / 1 test fail / **4 unhandled**：实际 Leads 挂载和 Create 点击通过，等待 LeadModal 字段控件超时；此时 epoch 0 / ACTIVE / READY，尚未填草稿、hidden 或 resume。unknown 为两次 `frappe.desk.search.search_link`；首捕获拒绝及四个 Vitest unhandled 均为 `RESOURCE_SUPERSEDED`，`resources.js:145`。不能把文本提及次数 7 当错误数量，亦不能把 runner 的 unknown_endpoint_lines 空数组当无未知请求。完整原始日志 SHA `eb61ecf349110702223f6cdd45a752f6b12cd69649b3d6c5a0c82f8a29d613dc`，source guards 前后通过。

静态核 FieldLayout 的 tabs→sections→columns→fields 与 fixture 结构一致；`Field.vue` computed 的 `placeholder: field.placeholder || field.label` 使 First Name 实际 placeholder 为 `First Name`，不是 getPlaceholder 末分支的 `Enter First Name`。测试 locator 修为 dialog 内该精确 input，不修改 Field。`Controls/Link.vue` 对 User 初始空 txt 的 search_link 自动读，transform 需要 value/可选 label/description 数组；按 [Frappe v15.125.0 search_link](https://raw.githubusercontent.com/frappe/frappe/v15.125.0/frappe/desk/search.py) 返回契约仅补 User 空查询的单个合成用户，其他 doctype/txt 仍拒绝，不添加生产允许项。

新增测试观察只保留已声明 doctype 枚举及调用源码位置：Form Script get_list 的同步发起位置和被 track Promise 的发起位置，仍执行原 track、不增加全局拒绝处理、不忽略 Vitest unhandled。实 SFC 静态链为 LeadModal→useDocument→getScript，以及 FieldLayout→useDocument、四个 Field→useDocument；getScript 在 document cache 命中前就调用。共享 createListResource 没有顶层 loading，只有 list.loading/fetched；成功空列表又不写 doctypeScripts，因此会重复 fetch 并使旧 generation superseded。listResource.fetch 丢弃 reload().finally 返回 Promise，也解释为何基础 resource 已观察拒绝后外层仍可能 unhandled；四项实际归属待新增来源位置确认，不能仅按计数认定全来自脚本。

待主控路由的最小生产方案（本轮未实现）：getScript 的自动读取以 `!scripts.list.fetched && !scripts.list.loading` 为门槛，使用底层 `scripts.list.fetch()` 的已观察 Promise，避免无消费 reload/finally 分支；成功空列表由 fetched=true 形成有效负缓存，并发调用只发一次，失败 fetched=false/loading=false 允许后续重试。需新增实际 getScript 的空缓存复用、并发单flight、首失败后重试成功、epoch 失效重读与不同 doctype/view 隔离 case，并重新做完整 SFC。现有严格函数内存实验已复现重复空读取的失败，但未闭合本次 SFC 四个 unhandled 归属，也未闭合 hidden/resume 因果，故暂不改生产。

M9 仅在隔离的 da2177 **43 entries 已 patch 源**中，原字节复制以下两文件：

- `sfc-resume.test.mjs` → `frontend/tests/unit/m24SafeResumeSfc.test.js`（相对 import 依赖此位置；新增 boot fixture 后须使用新候选 SHA）。
- `vitest.sfc.config.mjs` → `frontend/vitest.m24-sfc.config.mjs`（依赖同目录原始 vitest.config.js，不覆盖它）。

frontend cwd 执行：

```bash
yarn test:run --config vitest.m24-sfc.config.mjs tests/unit/m24SafeResumeSfc.test.js --reporter=verbose
```

本机仅 `node --check` 两个候选文件、diff 检查及生产零差异检查通过，无 compiler-sfc/vite/vitest。下一次仍须采退出码、编译/初始挂载/恢复失败层次、第一固定错误类别/位置和未知 API 列表；若失败于 fixture/编译/DOM 能力需先明确区分，不把此类失败冒充业务根因、不添加任意成功响应。此测试增量不要求重复完整 build/native，后续生产修复仍要独审及标准门槛。

## a8c64f5 冻结 oracle 与共同资源层最小修复

M9 run `f575e69931254d0a94d045738b49bf7d` 实际执行 a8c64f5：完整 App/Leads/Create/字段输入、hidden 的 SUSPENDED 和可见后的 resume 均已到达；首轮与一次重试最终均为 RETRY_COVERED / READ_SETTLE / READ_FAILED，unknown=[]、write requests=[]，Vitest 明确报告 **13 unhandled rejections**。首 superseded 发起链为 createResource auto→framework useOnboarding→AppSidebar，后继同 cache consumer 包括 GettingStartedBanner/HelpModal/Leads；另有 getScript→useDocument→FieldLayout/Field 的重复脚本读取。完整日志 SHA `d77c5d7bfb1bf79584bd62041892dbf91bea5c44c6b958896c6bcb29175605b9`。该运行未到显式恢复草稿断言，不是恢复通过。

保留该次测试及配置原字节作为修前/修后 oracle，SHA 分别为 `9a7443fe5c155b87f8b9a497f7aab0265ed306eddc2a59ca67c3449b3312341b` 与 `ad10e49f7ee3be2d9103dbe2f65a3ad2baed89c14c9407ae2f2a9b89c4f3b711`；本次不改 fixture 或断言。

经授权仅作两项生产修复：

- 共同 resources 层仅在 cache 命中、同请求 URL/method/参数数据与 fetcher、已知只读或显式 GET、无 makeParams/debounce/force、同一自动请求仍 pending 时共享原 Promise，不增加 generation。不同自动参数创建独立资源；显式 fetch/reload/submit、force 和自动写不合并，旧 epoch/旧 generation 检查及网络失败语义不变。此处的只读共享分类不是恢复请求授权，不改变 accountBoundary 的 reads 白名单。
- getScript 改用真实的 `scripts.list.loading/fetched` 和 `scripts.list.fetch()`；并发只读一次，合法空[]形成负缓存，失败不置 fetched，避免旧顶层 fetch 丢弃 reload/finally Promise。doctype/view 与 epoch 的 list cache 隔离仍沿用原严格机制。

在既有测试体系先复现红灯：双 consumer Promise 被替换、不同 params 错复用两项失败，实际完整 getScript 的并发断言失败且出现 superseded 未消费拒绝。修后四 suite **60/60 pass**，严格重放 **38 修改 + 5 guard** 与 after fixture real-runtime **15/15 pass**。新增覆盖同参数键序、不同参数、失败重试、force/reload/submit/写不合并、pending 旧 epoch 回调隔离、实际 getScript 并发/空缓存/可重试失败/网络失败保持遮罩/旧 setupScript 拒绝/零写。getScript 的普通 get_list 网络失败仍按现有策略进入 IDENTITY_REQUIRED，不宣称可在同一已终锁 epoch 重试；可重试失败以 DoesNotExistError 验证。实际 getScript 测试仅把 import.meta.glob 的模块清单设为空，不替换 getScript/list/resources/boundary，仍不等价完整 SFC。

生产 manifest 仍 43 entries；仅 resources.js 与 script.js after SHA 更新，before SHA、apply 源守卫、boundary、权限、草稿字段和恢复读白名单均未改。新候选仍须独审、M9 标准 build/native/bridge、原字节 SFC 修后实测和真实可见 UI，不以本地 60 项绿灯宣称现场闭环。已知 onboarding 读尚不在恢复 reads 中，另行静态核后端契约；本候选不先放宽。

## d27ff94 独审 P2-1：原始参数无损比较

独审确认旧 JSON replacer 会将 NaN/null、Date/ISO 字符串、数组 undefined/null 误判相同，而实际 resourceFetcher 接收的是原始 params，并非 JSON round-trip 结果。新增实际资源层对照回归在未修 d27ff94 上先红：两个 consumer 被合并，仅得到第一份参数结果。该问题是参数隔离缺陷，不认定为现场 READ_FAILED 的唯一原因。

requestKey 现先遍历原始值和数据属性描述符，再生成规范文本，不先 JSON.stringify 对象；仅明确无损的普通 JSON 值可共享。拒绝非有限数、负零、嵌套 undefined、稀疏/扩展数组、Date、toJSON、class、自定义原型、循环、函数、symbol、BigInt、访问器及非枚举字段；不合格返回独立 sentinel，原始参数仍原样交给各自 fetcher，不拦截正常请求。不调用用户 getter/toJSON；跨 realm 的原生 Object/Array 原型依据其原生 constructor/prototype 描述符核验。无 params 的顶层 undefined 保留默认语义；普通嵌套键序等价和 JSON 类型隔离保留。

新增回归使用同一个显式 resourceFetcher，核对两次实际输入引用与各自返回结果，包含上述碰撞、安全退化和副作用计数为零；原 force/reload/submit/自动写/失败重试/旧 epoch 断言保留。修后四 suite **62/62 pass**，严格重放 **38 修改 + 5 guard**、after fixture **15/15 pass**。本次仅改 resources payload、精确 manifest after、既有 controlled 测试及本文；getScript 修复、boundary/reads、SFC/config oracle 均原字节不变。仍需新 tip 独审，不沿用 d27ff94 的 hold 作为批准；新 SFC 和真实 UI 验收尚未执行。

## b2 修后 SFC 仍红：退休资源污染当前读取屏障

M9 run `fdeef6ea73c745d8a01fb8e2defd289c` 使用 b2 两生产 delta 和冻结原字节 SFC：仍 READ_SETTLE / READ_FAILED，但 unhandled 从 13 降到 0，Form Script 各 epoch 从两次降到一次；unknown/write 均为空。仅四条 tracked 拒绝来自 epoch2/4 的 HYDRATING 发起快照，各两条为 Link.vue 的 doctype/filters immediate300ms→reload206。栈走 assertRequest111→assertActive95，而非未声明请求109；search_link 原本就在 reads 中。onboarding 仅初始 epoch0 一次，没有恢复请求，本轮不扩大该方向。日志 SHA `7eb02e6d24b5ec0fbe5ac72832a71f0c5f66a72bdcf73db6a80b1e075af692f8`。

本地固定 SHA 的原始 Link reload 完整函数配合实际 resources/boundary 和明确受控300ms队列，复现创建epoch0资源在epoch2 HYDRATING触发：expected0/current2，两次请求均在transport前AbortError；当前epoch同search_link则成功。旧fetch无条件track使两拒绝污染新settle。保留该修前characterization：测试仅精确撤回新增归属门，仍预期RETRY_COVERED/READ_FAILED；修后同对照预期ACTIVE、旧transport/callback均0。此为受控timer因果，不是实际VueUse卸载/取消实测；真实SFC日志也未直接记录资源创建epoch，不将模拟值冒充现场值。

授权最小生产修复只有 resources.fetch 的一行：仅资源创建捕获的epoch等于boundary当前epoch时track。旧资源继续由原assertCurrent/assertRequest拒绝，不重新绑定、不放行、不按AbortError分类过滤；当前epoch任何失败仍进入原屏障。authAction原login/logout的assert豁免及可调用行为未变；仅同样遵创建epoch归属登记，不增加写重放。boundary/reads、Link组件、getScript、SFC/config均不变。

新增当前epoch受控延迟读回归验证：合法读让settle等待到响应；AbortError/网络/权限/未声明请求继续遮罩；已track后再隐藏失效，迟到成功不提交、不回调。四 suite **65/65 pass**，严格重放 **38 修改 + 5 guard**、after fixture **15/15 pass**。新tip仍需独审和M9原SFC修后实测，不能以本地通过称实际恢复闭环。

## b638 原 oracle 仍红后的独立 assertRequest 诊断副本

M9 run `d831f1be38284723af754b951817e79f` 的原字节 oracle 仍 READ_SETTLE/READ_FAILED，但 rejected=[]、unknown=[]、unhandled0，原四条 Link tracked 拒绝已消失；日志 SHA `9ae5e515e18e134eb87514b6b9c73810946cfc42c450ebad5ec88a0c31c46b59`。这不能证明读取屏障无错误。源码 hydrationError 仅由 assertRequest108 的未声明直接拒绝和 track120 的Promise拒绝赋值；frappeRequest 在创建/track Promise前先assertResume，故直接抛错可不经过原track观察。settleReads129闭包仅重抛；boundary内部没有assertRequest调用，外部均通过导出属性，包装该属性可覆盖直接入口，不能用对象spy替换不存在的内部settleReads入口。

新增独立 `sfc-resume-diagnostic.test.mjs`（SHA `affb298977934ae96f72d9c1e83ee10dea327768878cbfe910733f704f059ab9`），原a8 SFC/config不动。副本与oracle仅相差helper import、安装/清理透明wrapper和diagnostics附加assertionThrows；所有fixture、真实流程及断言保持。helper `sfc-request-diagnostics.mjs`（SHA `b619bd76d46f2010163ebc6ce7c3a02e70b0e3b3d34205ed4074f73d7830776d`）保存首次抛错、首次当前epoch HYDRATING抛错和首次RECOVERY_UNDECLARED，记录expected/current epoch、固定state/RPC method/错误类及无根路径源码位置；未知endpoint归OTHER_ENDPOINT，不输出参数、任意URL或原始异常文本。method是RPC endpoint枚举，assertRequest接口不提供HTTP方法，不能伪造GET/POST。原方法使用相同this/args调用、成功返回值原样返回、错误原对象重抛；诊断采集异常也不能吞掉原错误。

本地实际boundary回归确认直接poison在track调用数0时仍由原闭包settleReads抛同一Error对象、保持READ_FAILED；包装同时记录先前退休Abort和真正当前poison，不让首个旧异常遮盖后者。另核未知URL脱敏、源码路径无本机根目录、restore及原异常identity。四suite **66/66 pass**，相关语法/diff检查通过，生产payload/source_edits/manifest/apply和原oracle/config相对b638零差异；本机未执行新完整SFC，不重跑无生产变化的严格重放。

M9仅一次必要诊断执行：原字节复制诊断副本到 `frontend/tests/unit/m24SafeResumeSfcDiagnostic.test.js`，helper到同目录 `sfc-request-diagnostics.mjs`，独立原配置仍为 `frontend/vitest.m24-sfc.config.mjs`；执行 `yarn test:run --config vitest.m24-sfc.config.mjs tests/unit/m24SafeResumeSfcDiagnostic.test.js --reporter=verbose`。不要覆盖原 `m24SafeResumeSfc.test.js`，不要同时运行两个case或改生产诊断，不把诊断候选当修复。

## 2d1d978 诊断后的最小遥测集成修复

M9 诊断 run `f112128d5dd24dba92b0c4a84c172f9`（日志 SHA `232b4fa64a526f33dc7f82ddc5d4b236328a8a2697e9b638d13ec5f20c2aa525`）仍 exit1、READ_SETTLE/READ_FAILED。firstThrow、firstCurrentHydratingThrow、firstUndeclared 三槽一致：expected/current epoch2、HYDRATING，`frappe.utils.telemetry.pulse.client.boot_config` 被 RECOVERY_UNDECLARED 直接拒绝；栈为 accountBoundary108→frappeRequest94/95→frappe-ui call29→Framework pulse59→telemetry72。tracked rejected/unknown/write 均为空、unhandled0；epoch0 曾有 Pulse 网络请求，恢复 epoch2/4 则在网络前被拒。这明确定位本轮直接 poison，不把诊断运行冒充原 oracle 通过。

固定 Framework 936 源码确认 install 在取得 enabled:false 前已调用 fetchBootConfig；其 catch 会返回空配置，但不能撤销边界的 hydrationError，之后仍可能动态导入 CDN client。应用集成层采取一致策略：此 CRM SPA 正常启动及所有恢复重建均不安装可选 telemetryPlugin。相对 2d1d978 的全部生产代码 delta 仅为 main.js 删除 import、TELEMETRY_PLUGIN stage 和 app.use 三行，manifest 只更新该 payload after SHA；不修改 Framework、边界/reads、权限、资源归属、草稿或 getScript，不 catch 吞拒绝、不移到 ACTIVE 补发、不伪造 host/key。

Framework 模块默认 client=null、appName 未设、isEnabled=false，现有 useTelemetry.capture 在未启用/无 appName 时直接返回，getDistinctId 返回空值；保留组件调用为兼容 no-op。因此该 CRM 入口不再采集 Pulse 事件、ID/pageview，也不因安装启动 boot_config、CDN client 及其后续外发/计时器，降低可选外发和恢复耦合。此决策仅针对该 SPA 入口，不宣称全站遥测被关闭；已经运行旧 bundle 的旧页 client 不会因删除新代码停止，最终 UI 必须用新 bundle 的新页验收。不得为应用此变更而强刷丢失未提交草稿，应在安全的全页加载/受控换版后生效。

新增实际 main + Vue/Pinia + adapter/resources 回归：安装探针在修前记录 epoch0 ACTIVE 安装而红，修后正常启动及恢复均零安装、恢复 ACTIVE/uncovered，必要 get_doc_permissions/get 仍发起、无遥测或业务写请求；撤 read 权限后仍 IDENTITY_REQUIRED/covered。探针仅验证集成入口，不冒充实际 Framework client 执行。初始化 PROD/DEV 将可选插件设为“若安装即失败”仍 READY，安装序列不含遥测；仅删除生产已不可达的 TELEMETRY_PLUGIN 失败行，其余必要插件、router/socket/mount 等失败仍保留遮罩断言，并非降低业务门槛。

四 suite **67/67 pass**；严格重放 **38 修改 + 5 guard**、after fixture **16/16 pass**（证据 fixture 仅模拟 Git HEAD，不是真实构建）。main before SHA 仍 `c49ae1cc49039ded911ec6ab505afa2589f9119d4eb3376d87af9ca5b69fc609`，after 为 `504432dc1a9177f4987bc98a84c39859eadf4181e760841941bf78bb5996612d`；manifest 仍43 entries，所有 before/source_edits/apply 守卫不变。原 a8 oracle SHA `9a7443fe5c155b87f8b9a497f7aab0265ed306eddc2a59ca67c3449b3312341b`、config SHA `ad10e49f7ee3be2d9103dbe2f65a3ad2baed89c14c9407ae2f2a9b89c4f3b711` 及诊断副本/helper 原字节不变。仍须新 tip 独审、M9 原 oracle、标准 build/native/bridge 和真实新页 UI 验收；本机不启动共享环境，不宣称现场已闭环。

## 当前对账与最小原生生命周期验收（交 Terra）

已完成实现/测试任务：状态机与 epoch；当前列表参数、详情默认活动及创建表单只读重载/运行域隔离；同标签内存草稿、显式权限复核恢复与冲突保护；既有四 suite 扩展及严格补丁重放。复杂编辑器/移动页边界仍按上文，不新增支持。telemetry 已通过的代码审查结论不回退、不扩大清理范围。

M9 run `a6dc793202ef4d05b78edab68a2ca523` 对 1c586261 的原 a8 oracle/config 原字节执行：actual_test_exit0、1 file/1 test PASS、12.978s、unhandled0。实际草稿输入→受控 hidden/SUSPENDED/blocked→首次 visible/resume ACTIVE→unknown=[]→新控件无自动回填→显式 restore 后 firstName 相等→零 insert/set_value/onboarding 写断言全段通过。结果 JSON SHA `e5c1f91ca0598ffebe3ba6b4bb14805bd2cf673240e06a172b7434f00ad75bb5`、完整 log SHA `ec607921a8fe1cec718e99072c706c14ca8eb69774cb5527d59b02d527729323`，在 M9 `deploy/.runtime/m24-sfc-{result,single}-a6dc793202ef4d05b78edab68a2ca523.{json,log}`。这是完整组件测试的受控生命周期，不是原生浏览器切 tab。主控另确认 8c5 / 2c695eb2 构建通过；不重跑已绿 67/326 等测试，不把历史构建证据张冠李戴为新的现场生命周期证据。

最小环境配合：等 M9 独立升级演练释放窗口，由 Terra 提供当前授权的稳定目标/部署与 bundle 身份、同一浏览器标签的测试账号、无真实敏感内容的测试记录；不使用已关闭 URL、不切部署、不刷新已有草稿。验收必须是新 bundle 新页，旧 bundle 页不会自动停旧 Pulse client。仅需一轮用户自愿的原生标签切走/返回，或浏览器宿主已有的原生 tab 激活/窗口最小化与恢复能力；不打开侧栏、不抢前台。普通窗口遮挡或 focus 变化不保证 hidden。

当前内置 browser 工具契约：activate_tab 只选择控制目标，create_tab 可后台创建，均不保证 document.hidden；switch_tab 明确显示会话中的面板，不符合本轮禁止反复开侧栏/抢前台的限制。工具未提供独立的原生窗口最小化/恢复或保证 Page Visibility 的原生 tab 激活操作，因此不能承诺纯后台自动完成。Terra 若已有不显示面板且确实影响页面原生生命周期的宿主能力，先核其契约再只试一次；否则直接报告能力缺口，等待用户自然进行一次原生切换并配合读取，不以工具控制目标切换反复试探。

1. 在获准的新页正常 UI 打开 Lead 创建表单，输入唯一合成 First Name，不点保存；留一份字段/当前路由的脱敏证据。默认详情、列表筛选/分页等其他真实 UI 场景若无已有证据仍保留待验，不能由这一个创建 case 外推。
2. 用户或已核能力做一次真实原生切走/最小化，并在返回前允许后台只读 DOM snapshot（不显示面板、不输入脚本）看到“标签已暂停；未保存编辑仅保留在本标签内存…”遮罩且旧业务不可见。如已有合规只读观测可记录 data-crm-resume-state=SUSPENDED/data-crm-account-blocked 或真实 visibilityState，则一并保留；不为读取而注入 listener/改属性。没有暂停证据即“未触发生命周期/未验证”，不是 PASS。
3. 同标签原生返回，等恢复完成；正常判据是遮罩解除、当前页面/创建表单可用、新字段不自动回填，出现无值草稿提示。点击“恢复未提交编辑（不保存）”，原合成字段等值且没有执行保存。若已有允许的只读属性观测，应为 ACTIVE、READY/NONE、无 blocked；旧 C011100 PAGE_HIDDEN first-failure 是历史值，不是当前恢复失败判据。若约15秒后仍遮罩，记录屏幕固定 D020100 stage/failure 并停止，不循环 retry，不刷新丢草稿。
4. 不增加网络/业务注入。若环境已有不抢前台的只读网络采证，保留本轮必要身份/授权/只读请求及无 insert/set_value/onboarding 写证据；否则“零写请求”仅沿用组件测试结论，不冒称本轮真实网络已验证。真实撤权/换账号、离线重试、再次隐藏、旧响应、冲突及复杂编辑器安全退出仍需对应正常 UI/环境窗口，未有证据的项目不勾成现场通过。

禁止注入 visibility/pagehide/pageshow、调用 boundary.pause/resume/API 代替 UI、更换 oracle/验收条件或无限重试。最小正向 case 通过只关闭“真实 hidden→visible + 显式草稿恢复”这一缺口；整体交付任务继续保留，直至剩余真实场景按证据对账。代码 worker 本轮仅文档/协议更新，不操作浏览器、部署或 M9 环境。
