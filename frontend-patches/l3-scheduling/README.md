# L3 日程 CRM 导航补丁（D040300 / M30）

状态：导航补丁与源码级验证交付；R1 审查 P2-2/P2-3/P2-4 已修复（tip `4ff499e`）。M9 已在 full951 组合候选上完成标准生产构建与原生测试，主控/M27 报告记录了真实 CRM↔日程双向点击；本 worker 未重跑环境或构建，也不把该窗口扩大为完整 M24/M29 或 L3 通过（依赖 M24/M29 仍会阻止最终 merge），证据与边界见 §8。本补丁只增加正常 CRM 侧栏中的一个同源链接行，不实现排班功能，不提前 L3.5。

## 1. 已核事实（固定上游与补丁链）

| 项 | 值 | 依据 |
|---|---|---|
| CRM 源码 | `36bd8859f2a6345a620477bc708d0546e8c3f08a`（v1.90.0 谱系） | `deploy/Dockerfile` 固定提交，全仓一致 |
| 侧栏实现 | `frontend/src/components/Layouts/AppSidebar.vue` | 固定前端树导出（M20 `public-manifest.json`，`apps/crm/frontend/src`，471 文件） |
| 侧栏结构 | 顶部 `UserDropdown`；滚动列内依次 Search、Notifications、`CollapsibleSection v-for="section in allViews"`（All Views / Public Views / Pinned Views）；底部 `mt-auto` 为横幅、Help、折叠按钮 | 同上源码 |
| 链接组件 | `frappe-ui@1.0.0-rc.2` 的 `SidebarItem` 原生支持 `href`（`v-if="route || href"`，内部渲染普通 `<a href>`，与 RouterLink 分支同一内容） | 同一固定树 `node_modules/frappe-ui/src/components/Sidebar/SidebarItem.vue`、`Sidebar/types.ts` |
| CRM SPA 挂载 | `createWebHistory('/crm')`，全部业务路由在 `/crm` 前缀下 | 固定 `frontend/src/router.js` |
| 日程页面 | M29 交付 `apps/team_schedule/team_schedule/www/team-schedule.html`，站点根路径 `/team-schedule`；Guest 在 `team_schedule.py` 被重定向登录；页面内含 `<a href="/crm">返回原生CRM</a>` | wt-29 tip `cb0745ba…`（本行事实在 `cb0745` 重新核对；初版为 `13b9842`） |

因此入口必须是**同源整页 `<a href="/team-schedule">`**，不是 SPA 路由：`/team-schedule` 是服务端 www 页面，若写成 RouterLink 会被 `/crm` base 解析成 `/crm/team-schedule` 并落入 Invalid Page。补丁不改 `router.js`、不改 `main.js`。

## 2. 补丁内容：`AppSidebar.vue` 三处精确编辑

1. 新增图标导入：`import LucideCalendarClock from '~icons/lucide/calendar-clock'`。该图标名已在固定源码的 `components/Settings/Forms/fieldTypeIcon.js` 与 `components/Settings/WorkflowAutomations/workflowTriggers.js` 中使用，证明固定 `frappe-ui` 的 `lucideIcons` 插件（`vite.config.js` 的 `frappeui({ lucideIcons: true })` + pinned `lucide-static`）可解析；不新增依赖、不新增图标集合。
2. 解构 `usersStore()` 时增加 `isCrmUser`。
3. 在 Notifications 行之后、`All Views` 折叠区之前插入一行 `SidebarItem`：

```vue
<SidebarItem
  v-if="isCrmUser()"
  href="/team-schedule"
  :label="__('团队日程')"
  @click="selectItem($event, 'TeamSchedule')"
>
  <template #prefix>
    <LucideCalendarClock class="size-4 text-ink-gray-7" />
  </template>
  <span class="truncate text-sm">{{ __('团队日程') }}</span>
</SidebarItem>
```

`@click="selectItem(...)"` 复用侧栏原有行为：移动端抽屉先关闭，Ctrl/Cmd/Shift/中键点击不设高亮而由浏览器新开标签；普通点击走 `<a>` 默认的同源整页导航。`label` 同时给折叠态 tooltip 和可访问名。标签用 `__()` 包裹，当前语言包无此键时回落为“团队日程”（与 M29 页面标题一致）。

完整逐行差异见 `expected/AppSidebar.fixed-crm.diff`（仅供审查阅读，应用以 `manifest.json` 为准）。

## 3. 明确不做的事（隔离与防越权表述）

- 不修改 `frontend/src/main.js`、`session.js`、`store`/`resource`、`frappe-ui` 任何文件，也不改 `frontend-patches/c011000/**` 的补丁文件。M19/M20/M24 的身份初始化、账号缓存隔离与安全恢复边界原样保留。
- **注意：这不是“与 c011000 互不接触同一个上游文件”。** M24 变体的 c011000 清单本身把 `frontend/src/components/Layouts/AppSidebar.vue` 列为 `source_edits` 目标（before `940245e8…`，after `6dfc293d…`）。本补丁声明并验证这段**有序重叠**：c011000 先应用，本补丁以 M24 产物为第二基线再叠加；`check_apply.py` 直接读取 c011000 清单核验 before/after 衔接关系，而不是断言“无交集”；同一关系也写入 `manifest.json` 的 `upstream_overlap` 并在默认测试（无需另一工作树）中逐项断言。
- 不新增/改写路由，不新增页面、组件、状态或网络请求；没有新 API 调用，因此不引入新的授权判断。
- **菜单可见性不是授权**：`v-if="isCrmUser()"` 只用服务端返回的 CRM 用户列表决定是否显示；它既不授予也不校验 `/team-schedule` 访问权。真正授权仍在服务端：www 页面 `get_context` 的会话校验与 team_schedule app 的 ACL/接口校验（M25/M29 范围）。隐藏菜单不能替代这些检查，本补丁也不声称做到。
- Guest 不会看到该行：CRM SPA 只在身份门禁确认后挂载，Guest 由服务端重定向登录；Website（非 CRM 用户）在 `router.beforeEach` 被判非 CRM 用户，进入 Not Permitted 而不渲染 `Layout`/侧栏。`isCrmUser()` 是同一事实的第二道显示约束。
- 返回 CRM 的路径不由本补丁实现：M29 页面已有 `<a href="/crm">返回原生CRM</a>`，整页回到同一 CRM 站点。若 M29 后续改动该链接，需另行协调，不属本 patch 范围。

## 4. 应用协议与两种声明基线

补丁对 `frontend/src/components/Layouts/AppSidebar.vue` 做**锚点唯一匹配 + 全文结果哈希校验**，不模糊匹配、不提供 `--force`。接受两种精确基线（同一组编辑，分别产出各自声明的 after）：

| 基线 | before | after | 来源 |
|---|---|---|---|
| `fixed-crm` | `940245e8ab6465cd1a4bf19192c95856974e733813da15d1b175f5f588e1842d` | `e7e29bcb3c4eef499e9c32adb976719c0c547dbe849537ad2936ba24d459e048` | 固定提交原文件；与 c011000 声明的同一路径 before 一致 |
| `c011000-resume` | `6dfc293dfd44ed5b9673e8b65a019958bbc025b19abb415fa2b60d4e3561b2d0` | `e169f9d13cec9245390a8854b1dba8026227945abcaac03fb097473fca29a852` | 在固定原文件上运行 M24 `c011000/source_edits.py` 的 `AppSidebar.vue` 编辑（accountBoundary 导入 + `HYDRATING` 守卫）所得，等于 M24 声明的 after；wt-24 提交 `1a1aa0b` |

`fixtures/` 两个文件是**测试输入**（上游 AGPL-3.0 源码，仅用于重放校验，不直接部署）；`check_apply.py` 每次先校验 fixture 哈希等于声明的 before。

应用顺序：**先 c011000（集成分支当时携带的身份/恢复变体），再本补丁**。若集成链中 AppSidebar 已是第三种字节，apply 会以“Baseline mismatch + accepted hashes”拒绝并零写。此时：

1. `python apply.py --derive <该文件>` 只读输出候选 `before`、`after_candidate`、`anchors_verified_unique`、`declared_baseline`、`writes:false`、`apply_authorized:false`；它对**未登记字节**同样工作（只验证三个锚点各出现一次），但**不写 manifest、不授权 apply**。
2. 人工复核命中该文件的候选差异与来源。
3. 把该文件存为 `fixtures/` 新 fixture，并在 `manifest.json` 增加基线（before/after/来源），重跑 `check_apply.py`；`apply.py` 对未登记字节始终拒绝，绝不因 derive 放行。
4. 以上改动需新 tip 与独立复审。

三种模式互斥，语义固定：

| 模式 | 何时用 | 判定 |
|---|---|---|
| `--check` | **应用前**，且只在应用前 | 当前字节必须等于某声明 `before`；只读、零写 |
| `apply.py`（无标志） | 应用 | 同 `--check` 的校验全部通过后才逐文件临时文件 + `os.replace` |
| `--verify` | **应用后**，只读 | 当前字节必须等于某声明 `after`；未应用/未知/漂移都拒绝；不写文件。`--verify` 不替代 `--check`，`--check` 应用后会报 `Already applied`（重复写保护保留） |
| `--derive <file>` | 未知字节候选 | 只读候选，不写文件、不写 manifest、不授权 apply |

```sh
PATCH=frontend-patches/l3-scheduling
CRM=/home/frappe/frappe-bench/apps/crm
python "$PATCH/apply.py" "$CRM" --check   # 应用前：HEAD、基线哈希、锚点唯一性、结果哈希
python "$PATCH/apply.py" "$CRM"           # 应用：临时文件 + os.replace
python "$PATCH/apply.py" "$CRM" --verify  # 应用后只读：当前字节必须等于声明 after
```

拒绝条件：CRM `HEAD` 不等于固定提交；目标缺失/为符号链接/硬链接；父路径逃出 CRM；基线哈希不属于声明集合（`--check`/apply）或 after 不属于声明集合（`--verify`）；任一锚点出现次数不为 1；结果哈希与声明 after 不符；重复应用（当前哈希已是某基线的 after，明确报 `Already applied`）。检查全部通过前不写任何目标；不提供多文件原子事务，中途 I/O 失败必须丢弃该构建层并重建干净副本。

## 5. 已执行的验证

环境：Windows、Python 3.14、Node（本机），未安装依赖、未构建镜像、未部署、未访问运行实例。

```sh
python frontend-patches/l3-scheduling/check_apply.py                 # 本工作树 c011000（M19 变体，不触及 AppSidebar）
python frontend-patches/l3-scheduling/check_apply.py --c011000 <集成分支>/frontend-patches/c011000/manifest.json
node frontend-patches/l3-scheduling/sfc_check.mjs <fixed-crm-frontend-root>
```

1. `check_apply.py` **PASS**（上述两种 c011000 清单都跑过）：
   - 顺序重叠：读取 c011000 清单中的 `AppSidebar.vue` 条目，核验其 `before` 等于 `fixed-crm` before、`after` 等于 `c011000-resume` before、resume fixture 哈希等于该 `after`。对实际 M24 `1a1aa0b` 清单 PASS；对 M19 清单明确打印“该链无此目标”。不再断言“无交集”。
   - 重放：两种基线各自经真实 `apply()` 产出精确 after；`--check` 零写；漂移、目标缺失、错误 HEAD、重复应用全部拒绝且拒绝时零写；无残留临时文件；`c011000-resume` 结果仍保留 M24 的 `accountBoundary` 导入与 `HYDRATING` 守卫（`fixed-crm` 结果不含这些行）；`href="/team-schedule"` 与 `v-if="isCrmUser()"` 各恰好一处。
   - 文档完整顺序：`--check` → apply → `--verify` 通过且 `--verify` 零写；未应用、漂移、未知字节时 `--verify` 拒绝；应用后 `--check` 与再次 apply 仍报 `Already applied`（重复写保护未放松）。
   - `--derive`：登记基线与未登记字节（fixture 末尾加换行）都返回只读候选，`writes:false`、`apply_authorized:false`、未登记时 `declared_baseline:null`；锚点被破坏或文件已等于声明 after 时拒绝；derive 前后 manifest 字节不变；未登记字节仍被 apply 以 `Baseline mismatch` 拒绝。
2. `sfc_check.mjs` **PASS**：用固定前端树自带的 `vue/compiler-sfc` 对两种基线原文件与两种打补丁结果执行 `parse` + `compileScript` + `compileTemplate`，四者均无解析/模板错误；打补丁结果的 setup bindings 含 `isCrmUser`/`LucideCalendarClock`/`selectItem`，编译后模板含 `/team-schedule`。该检查使用固定导出树的编译器，不替代 Vite 构建。

**本 worker 未执行、但已由集成/浏览器 owner 在组合候选上执行**（本文件只引用，不重跑）：标准生产前端构建（Vite 8.2.0，3318 modules transformed，`✓ built in 7.59s`）、原生 Vitest 34 files/326 tests exit 0 与 bridge 1/1 exit 0、真实浏览器从 `/team-schedule` 返回 CRM 并实际点击侧栏再进日程。上述属于 §8 记录的组合候选验收，**不是**本 worker 自行重跑，也不等于完整 M24/M29/L3。仍未被这些证据覆盖：两名 Sales User 的完整双账号进入/操作/返回矩阵、Guest 与 Website 实际显示核对、撤权/注销后返回。语法/编译器检查不等于构建或产品入口验收；本补丁自身仍只对“入口存在且同源可达”负责。

## 6. 交 M9 的集成要求

1. **顺序与校验**：在固定 `36bd8859…` 源码上先应用集成分支的 `frontend-patches/c011000`（M19 或 M24 变体）；随后 `apply.py <CRM> --check`（应用前）→ `apply.py <CRM>` → `apply.py <CRM> --verify`（应用后只读，输出应为 `AppSidebar.vue = <fixed-crm|c011000-resume> after <hash>`）。**不要**在应用后再跑 `--check`：它只接受 before，会按设计报 `Already applied`；产物验证用 `--verify`。若集成链的 AppSidebar 是第三种字节，按 §4 的 derive → 人工复核 → 新 fixture/manifest → 复验流程处理，或直接停下交 tower 协调；`apply.py` 不会放行未登记字节。
2. **需要前端重新 patch/build**：是。`AppSidebar.vue` 属 CRM 前端源码，必须重新执行现有前端资产构建（`bench build --app crm`，沿用既有 preseed/资产清单强断言流程），不需要 `yarn install`、不新增依赖、不改 `package.json`/`yarn.lock`。该构建已在 full951 组合执行并通过（见 §8）。
3. **资产要求**：`team_schedule` app 已安装且 `apps/team_schedule/team_schedule/www/team-schedule.html` 存在，`/assets/team_schedule/team-schedule.css|js` 已构建可用（M29 资产，`bench build --app team_schedule` 或等价流程）；否则入口点击会落到缺失页面/资产，不能计通过。
4. **无新镜像层**：本补丁只多一个源文件改动，镜像需含已应用补丁的 CRM 源码与重建后的 assets；图标由 `unplugin-icons` 在构建期内联，无运行时外部图标请求。
5. 记录：CRM 提交、c011000 变体与哈希、本补丁提交、manifest/after 哈希、镜像 ID、`team_schedule` UI 版本（`cb0745ba24e119bf7d3e6ebe9c3d001a59ac4844`，原 13b9842 已返工）。

## 7. 保留的验收门（不得以本补丁替代）

- **已部分覆盖（单账号、单窗口）**：B 在 `/team-schedule` 实际返回原生 CRM，真实加载 CRM 页面并显示侧栏“团队日程”，再实际点击该侧栏回到 `/team-schedule`，未注入可见性或 JS、未以直接业务请求替代（M27 报告 tip `f4d7b0b`，见 §8）。这证明 M30 入口在真实组合候选上可达且可返回，但只覆盖一个 B 会话的一次往返。
- **仍保留**：两名仅 Sales User 的完整链路 `/login` → `/crm`（保留既有身份初始化门禁）→ 侧栏“团队日程” → `/team-schedule` 创建/修改/取消 → “返回原生CRM”回到同一 CRM，且未丢失既有 CRM 导航状态之外的可恢复内容。
- **仍保留**：Guest 直接访问 `/crm`、Website 用户访问 `/crm` 均不得看到业务侧栏或本入口；§8 的浏览器证据未覆盖这两种身份。
- **仍保留**：撤权/注销后返回 CRM 不得凭本入口绕过身份或权限校验（M19/M20/M24 边界保持）。
- 本补丁只覆盖“入口存在且同源可达”，页面内的 ACL、忙闲、ICS 等由各自 owner 的契约验收；完整 L3 不得以本补丁声称完成，L3.5 未开始。

## 8. 组合候选的构建与真实 UI 证据（引用 M9/M27，本 worker 未重跑）

2026-11-05 记录窗口 `full951-1e48de57805e47c889740323e8c31942`（站点 `full951-1e48de57805e.localhost:8092`）。组合 tip 取自 M9 的 source manifest；本 worker 未触碰容器、远端或数据库，也未重跑任何构建/测试。

| 组件 | tip |
|---|---|
| frontend（M24） | `951a4b9fe4fd41bd9db571c47d99bf0d85e4389a` |
| navigation（本补丁） | `4ff499ed5849347258b75b7daf42e349b484558b` |
| UI（M29） | `cb0745ba24e119bf7d3e6ebe9c3d001a59ac4844` |
| core / availability / ics | `a17401890cab85cacebbe9cd47197a9f68df0b80` / `5eae1f7c13786928ddddf515bc53825eaca94a33` / `4055de29d509e5ab4780568fc49c9b39a9fcc880` |
| resource_import / team_access | `faa5f0330ad54bd9f4d02bb498ea305651c95ed9` / `531bbaef50b4b674e5dc450dd311e466761c52ed` |

以下均为本机 ignored 运行材料（不是分发依赖），只记录核对结果：

| 证据 | SHA256 | 与本补丁相关的结论 |
|---|---|---|
| `P:/CRM/.tower/worktrees/wt-9/deploy/.runtime/full951-registry-1e48de57805e47c889740323e8c31942/source-manifest.json` | `298d8910f2144e8b951c9f9527fc409f21843eef1400872d306b2d02dd4df4ea` | `revisions.navigation` 恰为 `4ff499e…`，与上表一致 |
| `…/deploy/.runtime/final-harness-1e015508-r1/runtime-evidence/l3-scheduling-4ff499e.json` 与 `…/m24-951-1e48de57805e47c889740323e8c31942/frontend-patches/c011000/runtime-evidence/l3-scheduling-4ff499e.json` | `74787afa31373457e9b91fa8ea6f53e4e3317854670656558579df0762b75670`（两者相同） | 与本仓库 `4ff499e:frontend-patches/l3-scheduling/manifest.json` **逐字节相同**：构建使用的是本文档描述的补丁，不是变体 |
| `…/deploy/.runtime/m25-6a52b79158cb45b5b7aa4b18db67807b-m24-951-1e48de57805e47c889740323e8c31942-build.log` | `3a350ac92ac7220e25cf200d1a493514cb605275806e6b94ff8a9cfedae94818` | `bench build --app crm` 内 `vite v8.2.0 … 3318 modules transformed`、`✓ built in 7.59s`；`verify_m24_951.py` 在 before/switch/after 三阶段 PASS，断言已应用 `AppSidebar.vue` 的 SHA256 == `e169f9d1…`（本补丁 `c011000-resume` 声明的 after），并保留 `team-schedule.js|css` 与 app public 源逐字节一致 |
| `…/deploy/.runtime/m24-951-native-r3-result-1e48de57805e47c889740323e8c31942.json` | `8aef65f7b4d2e6b295523e11d6ee0c4bcb661b807caa464d961c035b609c0583`（与主控给定一致） | 同一 exact951 基础构建：native 34 files/326 tests exit 0、bridge 1/1 exit 0、无 unhandled。注意这是 CRM 既有前端测试套件，**不是**为本导航补丁新增的用例 |
| `…/deploy/.runtime/full951-registry-build-result-1e48de57805e47c889740323e8c31942.json` | `2e36bdfb0b7fc7cf87ed8f4e4c732d140cf514c3d1d95cead22cf7249a3df4e1` | `PASS five-app registered image …`；`fixed_image sha256:61a50c3c707ebac414dbf58d200dcb7949898c5dba930f4405ae63dda9bdbeb8`、`crm-local:full951-1e48…`，`base_image` 为受测的 `sha256:de4c74b2…`；labels 含 `crm.final.navigation=4ff499e`、`crm.final.frontend=951a4b9`、`crm.final.ui=cb0745` |
| `…/deploy/.runtime/compose.full951-1e48de57805e47c889740323e8c31942.json` | `7d68204f05e594e6ea8b1fc577f653a4a82b11a2accc3a17a53a78b933abb89a` | backend/frontend/websocket 均使用 `sha256:61a50c3c…`，即上表镜像 |
| `P:/CRM/.tower/worktrees/wt-27/docs/qa/browser-e7ef-d030300/full951/R1.md`（wt-27 tip `f4d7b0bd46a20d101da5c5d54c676994164293c1`，blob `519f13b9…`，内容 SHA256 `0e0add0e6b566ac27e17fc6f5872ff09dafdd0c900edca2a0013cc73e6cceb7d`） | 同左 | §“原生 CRM 双向导航与 UI 收尾”：B 从 `/team-schedule` 实际点击返回原生 CRM，加载真实 CRM 页面并显示侧栏“团队日程”（`text-7efb71fd…`）；再实际点击该侧栏（`elements-117a52de… e1`）回到 `/team-schedule`（`text-c58afc52…`）；报告注明未注入可见性或 JS、未以直接业务请求替代 |

**由此可核对到的闭环**：`4ff499e` 声明的 `c011000-resume` after（`e169f9d1…`）= M9 构建容器内实际 `AppSidebar.vue` 字节（三阶段守卫 PASS）= 真实 UI 中所见“团队日程”侧栏项，且生产 `bench build --app crm` 与既有 34/326 测试在该组合上通过。

**不扩大解释**：
- 单 B 账号、单窗口、一次双向往返；不是双 Sales User 完整矩阵，也未覆盖 Guest/Website 显示、撤权/注销后返回。
- M27 报告自身声明不等同完整 L3/M27；M24/M29 依赖仍会阻止最终 merge，这是正常状态，不绕过、不代签。
- 本 worker 未重跑环境或构建，未访问容器/远端；本节只是证据核对与文档记录，不新增验收结论。
