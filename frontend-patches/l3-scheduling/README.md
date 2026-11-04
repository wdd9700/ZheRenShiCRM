# L3 日程 CRM 导航补丁（D040300 / M30）

状态：导航补丁与源码级验证交付，待独立审查；**未运行 Vite/yarn 构建，未做真实浏览器往返验收**。本补丁只增加正常 CRM 侧栏中的一个同源链接行，不实现排班功能，不提前 L3.5。

## 1. 已核事实（固定上游与补丁链）

| 项 | 值 | 依据 |
|---|---|---|
| CRM 源码 | `36bd8859f2a6345a620477bc708d0546e8c3f08a`（v1.90.0 谱系） | `deploy/Dockerfile` 固定提交，全仓一致 |
| 侧栏实现 | `frontend/src/components/Layouts/AppSidebar.vue` | 固定前端树导出（M20 `public-manifest.json`，`apps/crm/frontend/src`，471 文件） |
| 侧栏结构 | 顶部 `UserDropdown`；滚动列内依次 Search、Notifications、`CollapsibleSection v-for="section in allViews"`（All Views / Public Views / Pinned Views）；底部 `mt-auto` 为横幅、Help、折叠按钮 | 同上源码 |
| 链接组件 | `frappe-ui@1.0.0-rc.2` 的 `SidebarItem` 原生支持 `href`（`v-if="route || href"`，内部渲染普通 `<a href>`，与 RouterLink 分支同一内容） | 同一固定树 `node_modules/frappe-ui/src/components/Sidebar/SidebarItem.vue`、`Sidebar/types.ts` |
| CRM SPA 挂载 | `createWebHistory('/crm')`，全部业务路由在 `/crm` 前缀下 | 固定 `frontend/src/router.js` |
| 日程页面 | M29 交付 `apps/team_schedule/team_schedule/www/team-schedule.html`，站点根路径 `/team-schedule`；Guest 在 `team_schedule.py` 被重定向登录；页面内含 `<a href="/crm">返回原生CRM</a>` | wt-29 `13b9842` 工作树 |

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

- 不修改 `frontend/src/main.js`、`session.js`、`store`/`resource`、`frappe-ui` 任何文件，也不改 `frontend-patches/c011000/**`。M19/M20/M24 的身份初始化、账号缓存隔离与安全恢复边界原样保留。
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

应用顺序：**先 c011000（集成分支当时携带的身份/恢复变体），再本补丁**。若集成链中 AppSidebar 已被第三种变体改写，apply 会以“Baseline mismatch + accepted hashes”拒绝并零写；此时用 `python apply.py --derive <该文件>` 得到新的 before/after 后再钉入 manifest，不得为通过检测而放行未知内容。

```sh
PATCH=frontend-patches/l3-scheduling
CRM=/home/frappe/frappe-bench/apps/crm
python "$PATCH/apply.py" "$CRM" --check   # 只校验：HEAD、基线哈希、锚点唯一性、结果哈希
python "$PATCH/apply.py" "$CRM"           # 逐文件临时文件 + os.replace
```

拒绝条件：CRM `HEAD` 不等于固定提交；目标缺失/为符号链接/硬链接；父路径逃出 CRM；基线哈希不属于声明集合；任一锚点出现次数不为 1；结果哈希与声明 after 不符；重复应用（当前哈希已是某基线的 after，明确报 `Already applied`）。检查全部通过前不写任何目标；不提供多文件原子事务，中途 I/O 失败必须丢弃该构建层并重建干净副本。

## 5. 已执行的验证

环境：Windows、Python 3.14、Node（本机），未安装依赖、未构建镜像、未部署、未访问运行实例。

```sh
python frontend-patches/l3-scheduling/check_apply.py
node frontend-patches/l3-scheduling/sfc_check.mjs <fixed-crm-frontend-root>
```

1. `check_apply.py` **PASS**：两种声明基线各自经真实 `apply()` 产出精确 after；`--check` 零写；漂移、目标缺失、错误 HEAD、重复应用全部拒绝且拒绝时零写；无残留临时文件；`c011000-resume` 结果仍保留 M24 的 `accountBoundary` 导入与 `HYDRATING` 守卫（`fixed-crm` 结果不含这些行）；输出中 `href="/team-schedule"` 与 `v-if="isCrmUser()"` 各恰好一处；manifest 只含一个目标、且不与 `c011000` 目标重叠。
2. `sfc_check.mjs` **PASS**：用固定前端树自带的 `vue/compiler-sfc` 对两种基线原文件与两种打补丁结果执行 `parse` + `compileScript` + `compileTemplate`，四者均无解析/模板错误；打补丁结果的 setup bindings 含 `isCrmUser`/`LucideCalendarClock`/`selectItem`，编译后模板含 `/team-schedule`。该检查使用固定导出树的编译器，不替代 Vite 构建。

**未执行（仍为验收门）**：标准 `yarn build`/`bench build --app crm` 与原生 Vitest；真实浏览器从 CRM 侧栏点入 `/team-schedule`、操作后返回 `/crm` 的完整往返；双普通账号、Guest/Website 实际显示核对。语法/编译器检查不等于构建或产品入口验收。

## 6. 交 M9 的集成要求

1. **顺序**：在固定 `36bd8859…` 源码上先应用集成分支的 `frontend-patches/c011000`（M19 或 M24 变体），`--check` 通过后再应用本补丁，再 `--check` 复核。
2. **需要前端重新 patch/build**：是。`AppSidebar.vue` 属 CRM 前端源码，必须重新执行现有前端资产构建（`bench build --app crm`，沿用既有 preseed/资产清单强断言流程），不需要 `yarn install`、不新增依赖、不改 `package.json`/`yarn.lock`。
3. **资产要求**：`team_schedule` app 已安装且 `apps/team_schedule/team_schedule/www/team-schedule.html` 存在，`/assets/team_schedule/team-schedule.css|js` 已构建可用（M29 资产，`bench build --app team_schedule` 或等价流程）；否则入口点击会落到缺失页面/资产，不能计通过。
4. **无新镜像层**：本补丁只多一个源文件改动，镜像需含已应用补丁的 CRM 源码与重建后的 assets；图标由 `unplugin-icons` 在构建期内联，无运行时外部图标请求。
5. 记录：CRM 提交、c011000 变体与哈希、本补丁提交、manifest/after 哈希、镜像 ID、`team_schedule` 版本（13b9842）。

## 7. 保留的验收门（不得以本补丁替代）

- 两名仅 Sales User 合成账号：`/login` → `/crm`（保留既有身份初始化门禁）→ 侧栏“团队日程” → `/team-schedule` 创建/修改/取消 → “返回原生CRM”回到同一 CRM，且未丢失既有 CRM 导航状态之外的可恢复内容。
- Guest 直接访问 `/crm`、Website 用户访问 `/crm`：均不得看到业务侧栏或本入口。
- 撤权/注销后返回 CRM：不得凭本入口绕过身份或权限校验（M19/M20/M24 边界保持）。
- 本补丁只覆盖“入口存在且同源可达”，页面内的 ACL、忙闲、ICS 等由各自 owner 的契约验收；完整 L3 不得以本补丁声称完成，L3.5 未开始。
