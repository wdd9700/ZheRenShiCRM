# D020100 Safe Tab Resume — 候选实现与验收门槛

状态：本地实现和固定源重放已完成；**标准构建、独立审查及正常可见浏览器验收待 tower/M9，未称完整交付或部署可用。**

## 起点与决策

- foundation `36521b0`，未 revert/amend/merge/cherry-pick。M20 已审 `87386bc8493b9e0605224adfdcf3aacd42595d6f` 的初始化诊断、允许值列表、first-failure 与 DEV Promise 错误链作为前置保留，归属 M20。
- D020100（Provisional）：采用明确页面/草稿适配器、新 Vue/Pinia/socket 运行域与模块缓存隔离。不遍历资源 reload、不自动重放写请求、不做通用 Vue 快照、不仅凭同 user 揭罩。
- 恢复顺序：先遮罩 → 捕获允许的同标签内存草稿 → 旧 epoch 失效/停止运行域 → 服务端身份 → 当前页面 fresh read/create 权限 → fresh 只读请求和新域挂载 → mounted 页面/详情活动区登记 → 等待读请求与 Vue 更新达到稳定修订号 → 第二次服务端身份和 epoch 复核 → 揭罩。恢复最多 15 秒，失败遮罩且可显式重试；再次 hidden 使旧恢复失效。
- 初始 hidden 不发身份请求/不挂载；BFCache 回归走相同屏障。账号广播、cookie 变化、Guest、身份变化、认证/权限拒绝终止恢复，清草稿和旧敏感引用。

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

`frontend-patches/c011000/manifest.json` 当前包含 **36 个修改目标（9 payload + 27 strict source edits）及 5 个只读 guard**。`apply.py` 仍要求真实 CRM HEAD `36bd8859f2a6345a620477bc708d0546e8c3f08a` 和每个 before SHA 完全匹配；所有目标检查完成才写。source edits 每个 anchor 必须唯一，输出 after SHA 同样校验；拒绝漂移、缺文件、重复应用、链接目标与已有临时文件。此补丁面向固定未 patch 源，不可直接覆盖 M19/M20 已 patch 运行目录。

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
- real-runtime source loader 严格接受每个 manifest before 或 after SHA：before 转换并复核 after；after 原字节执行；其余 drift 拒绝。因此 bridge 可运行已 patch cwd，不会重复套 source edit。`C011100_SOURCE_ROOT` 可分离只读源码证据，`C011100_FRONTEND_ROOT` 只为既有依赖定位；`check_apply` 在设置后者时自动再以重放后的 after fixture 运行真实测试。生产 apply 的 before 门槛没有放宽。Python 默认 Windows `python`、Linux `python3`，可 `C011100_PYTHON` 指定。

## 尚待门槛

本机固定导出缺 vite/esbuild/vitest/TypeScript/compiler-sfc/vue-router；未安装依赖、未启动 WSL/容器/远端。需 tower 协调 M9 在既有固定 Linux 构建环境用候选 commit 单次 clean baseline apply + 标准构建（包含完整 SFC、真实依赖解析和 Vitest bridge），有失败必须回修，不降低 hash/构建门槛。

独立审查后由 M9 集成，正常可见浏览器至少验证：默认活动详情、列表筛选/分页、创建草稿、切 tab 往返与再次隐藏、网络失败重试、账号切换/注销/撤权、旧请求晚到、冲突不覆盖和复杂编辑器安全退出。不能改 visibility 或用后台工具绕过；未通过这些不得称完整交付。
