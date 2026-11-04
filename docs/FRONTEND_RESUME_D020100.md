# D020100 Safe Tab Resume — 候选实现与验收门槛

状态：本地实现和固定源重放已完成；**标准构建、独立审查及正常可见浏览器验收待 tower/M9，未称完整交付或部署可用。**

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

## 尚待门槛

本机固定导出缺 vite/esbuild/vitest/TypeScript/compiler-sfc/vue-router；未安装依赖、未启动 WSL/容器/远端。需 tower 协调 M9 在既有固定 Linux 构建环境用候选 commit 单次 clean baseline apply + 标准构建（包含完整 SFC、真实依赖解析和 Vitest bridge），有失败必须回修，不降低 hash/构建门槛。

独立审查后由 M9 集成，正常可见浏览器至少验证：默认活动详情、列表筛选/分页、创建草稿、切 tab 往返与再次隐藏、网络失败重试、账号切换/注销/撤权、旧请求晚到、冲突不覆盖和复杂编辑器安全退出。不能改 visibility 或用后台工具绕过；未通过这些不得称完整交付。
