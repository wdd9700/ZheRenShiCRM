# D020100 Safe Tab Resume — 暂停检查点（未交付）

状态：**实现中，因用户 Windows 更新要求于 2026-11-04 暂停；不得构建部署或称完整交付。**

## 起点与已落盘内容

- foundation 是 tower 提供的 `36521b0`，没有 revert/amend/merge/cherry-pick。
- 已核 M20 精确已审 `87386bc8493b9e0605224adfdcf3aacd42595d6f` 的 main/accountBoundary/初始化测试逻辑。本轮 main/accountBoundary 含 M20 stage/failure allowlist、first-failure、DEV Promise 错误链；这是 M20 前置归属，不计作本轮独创。
- 已写暂停/恢复状态机：hidden 使 epoch 失效，visible 合并恢复；初始 hidden 不发身份请求；服务端身份 → fresh 当前授权读取 → 新运行域只读 hydration → 第二次身份/epoch核验 → 揭罩；失败保持可重试安全界面。
- generic/list/document resource 按 epoch 隔离；旧成功/旧错误不得进入新 epoch。资源同步 `promise` 发布契约及原 18 项回归保留；无写请求自动重放。
- `safeResume.js` 是显式列表/文档/创建草稿 registry，只保留内存字段差异，不持久化、广播、上传草稿。fresh 权限复核后主动恢复，不自动保存；冲突不覆盖。
- `resumeRuntime.js`/main 采用旧 app/Pinia/socket 停止及新运行域。`source_edits.py` 提供固定上游唯一 anchor 的显式修改，拟清 documents/controllers/assignees/permissions、meta/script cache，接列表、Lead/Deal、快速创建与直接 frappeRequest。

## 当前验证（仅检查点证据）

在 wt-24 执行：

```bash
node --experimental-vm-modules --test frontend-patches/c011000/controlled.test.mjs frontend-patches/c011000/initialization.test.mjs frontend-patches/c011000/resume.test.mjs
```

结果 **33 tests / 33 pass / 0 fail**。覆盖原 18 项资源/默认视图/深链接/Promise 回归、M20 初始化诊断、hidden-visible、重复恢复与旧请求、再次 hidden、账号/Guest/广播/cookie、BFCache、网络重试、草稿权限/冲突/创建权限。

这是 VM/受控测试，**不是实际 CRM 页面的完整 Vue/Pinia 渲染验收**。

只读复用了 tower 指定固定导出：
`P:/CRM/.tower/worktrees/wt-9/deploy/.runtime/m20-public-frontend-evidence-3828e3eb572143f99e2420809fd5f1b2/apps/crm/frontend/`。
已用 package.json 与真实 require 核 Vue `3.5.32`、Pinia `2.3.1` 和 real renderer 可用；未修改导出、安装依赖、访问 WSL/容器/runtime 服务或操作浏览器。

该导出 7 个原 payload 是 M19 patched（main `82052368…`），不是原始 baseline。新涉及的 9 个上游文件可读取，当前 source_edits 全部唯一 anchor 转换通过。`@babel/parser` 可用，esbuild/vitest/TypeScript/compiler-sfc 顶层包不可用。标准构建仍须后续交 M9；不能静默安装工具。

## 已知未完成 / 恢复时必须先做

1. **manifest 尚为旧版 hash/7 payload 清单**，故当前 apply 必须拒绝，不能拿本检查点部署。需更新所有 changed payload after hash，把 `safeResume.js` → `frontend/src/data/safeResume.js`、`resumeRuntime.js` → `frontend/src/resumeRuntime.js` 及 source_edits 9 个目标加入 exact before/after manifest。`apply.py` 已有 edits 分支，但尚未 replay 验证。`check_apply.py` 仍固定 7 文件、只核 payload，需要扩展。
2. main 新增 `resumeRuntime`、`nextTick`、`disposePinia`：新 `initialization.test.mjs` 已适配，**真实运行测试 `real-runtime.test.mjs` 尚未带入/扩展，vitest bridge 亦未升级**。恢复时按 M20 原文件扩展，不把受控 fixture 视作真实渲染测试。
3. `safeResume.resumeListParams` 已定义，但 **ViewControls 尚未调用**，当前列表筛选可能回到保存视图，必须接入或明确拒绝不一致恢复。不要把旧 params 静默丢弃。
4. 草稿字段过滤保守仅 permlevel 0 标量，未支持 Table/附件/复杂子表。`planDrafts` 的 permlevel 检查尚需与 capture 使用 `Number(field.permlevel)` 一致。复杂字段差异不得被忽略后丢弃，应检测并保持原页面遮罩。
5. module-cache/source-edits 与 direct frappeRequest 的真实异步回调边界、权限响应结构（含创建 `get_doc_permissions`）、新 app/router 重入、hydration 稳定屏障尚需真实 Vue/Pinia + 固定上游执行验证。三轮 nextTick 不能未经实证便宣称覆盖所有动态 async component。
6. hidden 暂停应 **先遮罩再捕获/销毁 app**；当前 pause 顺序尚需调整和测试。停旧运行域/invalidator 过程中异常的 fail-closed 顺序亦需加强。
7. main DEV 请求已以捕获 epoch 验证；boot 的原子性/初始化期间 hidden、恢复期间再次 hidden仍需真实测试。对 direct request hydration early sync throw 的计数/错误捕获需核。
8. 当前只拟支持桌面 Leads/Deals 列表、Lead/Deal `#data`、Lead/Deal 快速创建。活动/邮件/Comment/Note/Task/导入/设置/移动详情/其他 dialog 明确未支持，保持遮罩与旧内存，不得冒称全站恢复。用户任务要求的列表/详情/创建是否可接受这一最小边界，需最终向 tower 如实协调，不能擅自缩交付。
9. 整个 source-edits 输出还需语法/导入路径/固定 before hash 检查，尤其新引用文件的层级。不修改上游导出；测试临时产物仅放 wt-24 的 scope 内并清理。
10. 独立审查、M9 标准容器构建及真实正常可见窗口的 tab/账号切换/撤权/冲突验收全部未做。不得改 visibility 绕锁或以后台工具替代真实可见窗口。

## 临时决策与复评

D020100（Provisional）：选择明确 route/draft adapter + 新运行域及模块缓存显式失效，拒绝遍历资源 reload（可能写入）、拒绝通用 Vue 快照、拒绝仅同 user 揭罩。优点是可审计、不自动重放写；代价是支持边界窄、需逐页面真实验证。当前置信度中低，以上真实运行证据补齐后复评。未改全局 DECISION_LOG，因本 mission scope 不允许；交 tower 最终汇总。

当前没有必须交用户拍板的新增授权/价值卡点；暂停来自用户系统更新指令，不是产品已交付。保持 worktree 和证据，不删除。恢复须由 tower 在用户明确更新结束后继续安排。
