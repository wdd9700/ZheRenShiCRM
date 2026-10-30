# M6 团队访问隔离验证与修复边界

日期：2026-10-31
环境：Frappe CRM 1.90.0 / Frappe Framework 15.125.0，`crm.localhost`，`http://127.0.0.1:8088`

## 1. 结论与当前可用边界

**团队私域验收尚未通过。** 两个真实普通账号的 HTTP/API 验证已经证明：`CRM Lead` 可以复用原生负责人/分配机制形成私域与协作边界，但 `FCRM Note` 原生不继承关联 Lead 的权限，且共享 Lead 的原生活动时间线会返回未共享备注。不能把管理员 CLI 成功、单账号登录或逐记录临时授权当作团队隔离完成。

在独立安全扩展完成前，只允许以下临时操作边界：

- CEO 私人资源和私人备注只放在**独立的私有 `CRM Lead`**中；`lead_owner` 必须是本人。私人备注可暂用该私有 Lead 的 `company_description`，不要把私人和正式资料混在同一共享 Lead。
- 正式业务资料使用另一条共享 Lead。需要让普通成员在列表中看到并协作时，使用原生 **Open ToDo 分配**；`DocShare` 单独只验证了详情/写入，标准 Lead 列表仍可能为空。
- **不要把私人原文放入 `FCRM Note` 或 `CRM Task`，也不要把私有 Note 关联到共享 Lead。** 共享父记录不等于子记录已授权。
- `CRM Organization`、`Contact` 当前只用于默认团队共享的正式资料，不用于 CEO 私域。
- 普通成员只授予 `Sales User`。`Sales Manager` 不在销售层级时可看到全部 Lead/Deal，`System Manager` 更是管理边界，二者都不是最小普通团队角色。
- M7/导入服务现阶段仅处理 Lead，并逐对象检查当前真实用户的 create/read；私密原文不得写入 Note。仅认证后用 Administrator ORM 写入不属于用户权限验证。

## 2. 实际角色、owner 与分享语义

已直接读取运行版本的 DocPerm 和权限钩子：

| 对象 | `Sales User` 角色权限 | 原生记录级收敛 | M6 结论 |
|---|---|---|---|
| `CRM Lead` | create/read/write/export/share 等 | CRM 钩子使用 `lead_owner`：本人或非取消 ToDo 分配；不是仅看数据库 `owner` | 私域 Lead 的详情、越权修改和私有父时间线拒绝通过；共享协作可用，但 DocShare 列表语义不完整 |
| `CRM Deal` | 同类角色权限 | 钩子使用 `deal_owner` 和 ToDo 分配 | 源码确认，未做本轮完整 HTTP 验收 |
| `FCRM Note` | create/read/write/export/share 等 | 无 owner 钩子、无关联 Lead 权限继承 | 已复现越权读取和修改；共享父时间线泄露未共享 Note |
| `CRM Task` | create/read/write/export/share 等 | 无对应私域钩子 | 原生 DocPerm 与时间线原始查询构成风险；本轮未完成 Task 专项 HTTP 验证 |
| `CRM Organization` | create/read/write 等 | 无 owner 收敛钩子 | 默认团队共享，不能存放私域 |
| `Contact` | `Sales User` 有 create/read/write 等 | 虽有其他角色和 `All/if_owner` 条目，但 Sales User 的全量权限使其不是私域 | 默认团队共享，不能存放私域 |

补充事实：

- 运行站点存在 `Sales User`、`Sales Manager`、`System Manager`，不存在名为 `CRM User` 的角色。
- CRM 的 Lead/Deal 钩子对 `Administrator`、`System Manager` 放行；不在销售层级中的 `Sales Manager` 也放行。
- `DocShare` 可在角色/控制器权限失败后补充 read/write，因此“详情可分享”成立；但 Lead 列表查询仍使用 owner/assigned 条件，不能据此推断分享记录一定出现在列表。
- `User Permission` 是允许列表限制，不会自动修复 CRM 自己用 `frappe.db.get_all` 实现的关联时间线。

## 3. M6 合成夹具与凭据边界

只使用以下专用账号，均为 `System User` + 唯一显式业务角色 `Sales User`，邮箱是不可投递的 `.invalid` 合成地址：

- `m6-a@example.invalid`：私域拥有者 A。
- `m6-b@example.invalid`：另一普通成员 B。

对象均使用 M6 标识：私有 Lead、共享 Lead、私有 Note、共享 Note，以及专门关联共享 Lead 的未共享 Note。配置还使用 M6 专用 `DocShare`、`User Permission` 和描述为 `M6-SHARED-LEAD-ASSIGNMENT` 的 ToDo。所有内容都是合成哨兵，不是真实客户资料。早期幂等缺陷产生的少量 M6 重复夹具按“不删除记录”要求保留，后续配置会复用最早记录，并在 guarded 阶段停用旧重复夹具对 B 的分配/分享/允许项。

配置和验证由 `tools/access/m6_team_access.py` 完成：

- 每次运行在容器内生成新的高熵临时密码；密码仅存在子进程与父进程内存，不写文件、不打印、不提交。
- 不读取 `.env`、现有密码、令牌或会话；HTTP 只使用新生成的 M6 普通账号，不建立 Administrator HTTP 会话。
- Administrator 仅在容器配置阶段用于创建/更新 M6 夹具；所有权限断言都由 A/B 的真实 Cookie 会话和 CSRF 完成。
- 不修改 Administrator、全局角色、调度器或 M5 对象，不发送邮件、不删除记录、不重启服务。
- 为遵守“不删除记录”，脚本切换阶段时只停用/启用 M6 自己的 User Permission、DocShare 和 ToDo；这些逐记录配置是实验对照，不是生产修复。角色子表也不清空，发现非预期角色会中止。

M7 负测另用 `tools/access/m7_access_negative.py`，账号为 M6 自有的 `m6-sales-manager@example.invalid` 和 `m6-system-manager@example.invalid`，并复用 M6-A。它们只用于授权负测和指定浏览器验收，不是给真实用户加权。

## 4. 可重复运行

在 Windows 项目根目录执行，需第一套 `Ubuntu-24.04`、现有 `crm-mvp-v15-backend-1` 和回环站点可用：

```bash
# 拟议限制复验；当前应因 activities 泄露返回非零
python tools/access/m6_team_access.py --phase guarded

# 原生默认行为复现；越权断言失败是漏洞证据，不是测试工具故障
python tools/access/m6_team_access.py --phase default

# M7 匿名/普通角色/经理/跨会话/撤回负测
python tools/access/m7_access_negative.py
```

两个阶段使用**独立进程**运行。`--phase both` 仅用于诊断。脚本默认是 `guarded`，可使用 `--base-url` 指定同一受控站点的其他回环入口。最终交付时实例保留在 **default 原生状态**：M6 Note User Permission 和 Note DocShare 停用、共享 Lead 的 M6 ToDo 为 Cancelled，避免把临时 workaround 误认为修复。

M6 覆盖的 HTTP/API 边界：

- 真实登录与 `frappe.auth.get_logged_user` 身份核对；从 `/crm` 会话页面/Cookie 取得 CSRF。
- Lead、Note 的标准 REST 列表和详情；关联 Note 查询。
- B 对私有 Lead/Note 的 PUT 拒绝及 A 回读未篡改；B 对共享 Lead/Note 的协作更新及 A 回读。
- `crm.api.activities.get_activities` 的私有父拒绝、共享父的子 Note 过滤。
- `frappe.desk.reportview.export_query` 同步 CSV，包括普通导出和 `selected_items` 定向导出；不使用后台导出或邮件。
- 私有 Lead 的 `company_description` 哨兵必须不出现在 B 的导出中。

任一安全断言失败即退出 1。输出只含检查名称和安全状态，不含密码、Cookie、CSRF、receipt 或客户正文。

## 5. 已实证结果与未决项

### 5.1 默认原生行为：真实 HTTP 已复现

- B 直接 GET 私有 Note 返回 200；PUT 私有 Note 也返回 200。A 的 Lead 私域详情/写入拒绝则通过。
- B 的 Note 列表和按共享 Lead 过滤的关联 Note 查询包含未共享 Note。
- B 可读取共享 Lead 时，`get_activities` 返回关联该 Lead 的未共享 Note 正文。私有 Lead 本身的 activities 请求会拒绝，但**只检查父权限不够**。
- 仅给 B `DocShare` 的共享 Lead 可打开详情并写入，标准 Lead 列表却为空；guarded 阶段增加 Open ToDo 后列表和协作通过。

### 5.2 最终 guarded 结果：14 项通过，仅 activities 失败

最终独立 guarded 运行为 **14 PASS / 1 FAIL**。Lead/Note 列表、详情、关联 resource、私有写入拒绝、共享写入协作、Lead/Note CSV 及 `selected_items` 均通过；唯一失败是共享 Lead 时间线仍泄露未共享 Note。该结果说明逐记录配置能覆盖部分 Framework REST 路径，但绝不是原生 activities 的修复，团队验收仍失败。

早期疑似“缓存不一致”已查明为测试夹具问题：CRM 分配/负责人逻辑会改变 `lead_owner`，下一次按标题+原负责人查找时误建重复 Lead/Note；通过 `save()` 改负责人还会重组 DocShare。现脚本按稳定 M6 标题复用最早记录、避免通过文档保存改负责人，并只停用历史 M6 重复项，不再把该现象归为未知缓存问题。

### 5.3 测试请求本身已修正的问题

- 普通角色调用 `frappe.sessions.get_csrf_token` 返回 403，改为项目既有烟测使用的 `/crm` 页面/Cookie 方式，不代表提权。
- 导出最初把 fields 错传为二维数组并多传空 `report_name`，导致 500；改为字段名数组并移除该参数后正常返回。上述 500 不计为权限通过或泄露证据。
- Frappe CSV 会把下划线显示为 `\_`；断言先规范化该转义，再同时检查记录 ID 与私密正文，避免共享哨兵假失败和私密哨兵假通过。

### 5.4 M7 负测与错误响应设置

经 tower 明确授权，本站 `System Settings.allow_error_traceback` 从 **1 改为 0** 并 clear cache。首次普通 save 被既有 `language`、`time_zone` 必填校验阻断且未提交；随后保留这些字段原值，以 `ignore_mandatory` 仅保存目标项成功。操作只对目标字段赋值，未修改其他字段；但未做全字段前后快照，不能声称完成全字段哈希核验。回退是在同一受控窗口将该单值恢复为 1 并 clear cache。此设置只收敛 HTTP 错误详细程度，不等于关闭服务端日志；本轮未读取或输出日志。

最终 `m7_access_negative.py` 为 **12 PASS / 0 FAIL**：System Manager 页面/preview 通过；Sales User、Sales Manager 和匿名页面/API 拒绝；有效 preview receipt 不能跨用户或匿名 apply；角色从 System Manager 改为 Sales User 后有效 receipt 返回安全 403；禁用账号后原会话返回 417，但无实际 `exc`/`exception` 堆栈、源码路径/行号、候选或秘密；preview 与所有拒绝 apply 均未写业务 Lead。断言允许纯 `exc_type=ValidationError` 类型名，仍禁止异常堆栈和敏感内容。

“System Manager 但无必要 create”未测：三个导入实体的 System Manager 均有 create，不改全局 DocPerm 无法安全构造。Sales User 和 Sales Manager 虽有 create 仍被入口拒绝已验证。专用 System Manager 最终恢复 `enabled=1` 和 System Manager；指定浏览器标签已显示 `/resource-import`，未提交导入。这只是页面就绪，不是完整视觉验收。

## 6. 独立安全扩展的最小修复边界

应由独立安全 mission 新建专用扩展 app；不修改 Frappe/CRM 核心，不修改 M7 导入 app，不用全局 DocPerm 放宽或逐条 User Permission 代替修复。

### 6.1 Note/Task 列表、详情、写入与导出

在扩展 app 的 `hooks.py` 注册：

```python
permission_query_conditions = {
    "FCRM Note": "resource_access.permissions.note_permission_query_conditions",
    "CRM Task": "resource_access.permissions.task_permission_query_conditions",
}
has_permission = {
    "FCRM Note": "resource_access.permissions.has_note_permission",
    "CRM Task": "resource_access.permissions.has_task_permission",
}
```

建议语义：

- Note：仅 `owner` 或显式 DocShare；Task：仅 `owner`、有效 `assigned_to` 或显式 DocShare。是否允许经理查看必须由业务另行决定，不能默认给 `Sales Manager` 全量私域。
- `System Manager` 的管理旁路要作为显式管理边界保留；普通角色不得因关联父记录可读而自动获得子记录权限。
- `has_permission` 对未授权者返回 False，让 Framework 继续执行原生 DocShare read/write 补充；对 owner/有效负责人返回 True。create/write 时若提供父关联，还应验证当前用户对该父记录的 read，防止向不可见父记录挂接内容。
- 列表查询条件必须显式包含 owner、有效负责人及 `frappe.share.get_shared(..., rights=["read"])` 的名称。不能只写 owner 条件后假设 DocShare 会自动并入列表；Lead 已实测证明该假设不成立。
- CSV 必须复用同一 `DatabaseQuery` 条件，并专项测试 `selected_items`；不能只检查页面列表。
- 扩展生效后不再叠加 M6 的逐记录 User Permission。必须验证普通成员新建自己的 Note/Task 后默认可读、另一成员默认不可读，避免“允许列表导致新记录创建后自己也不可读”。

### 6.2 原生 activities 必须单独覆盖

上述 hooks 不会约束 CRM 源码中的 `frappe.db.get_all`。扩展还需在 `hooks.py` 使用官方白名单覆盖入口，例如：

```python
override_whitelisted_methods = {
    "crm.api.activities.get_activities": "resource_access.api.get_activities",
}
```

实现必须：

1. 保留 Lead/Deal 父记录 read 检查。
2. 对 `get_linked_notes`、`get_linked_tasks`、`get_linked_calls` 涉及的每个子对象执行权限过滤；列表走权限查询，单对象用当前会话 `frappe.has_permission(..., doc=...)`。
3. 同时过滤返回的 `notes`、`tasks`、`calls` **以及由这些对象派生的 activities**。只过滤 `notes` 数组不够，添加/置顶/版本活动仍可能泄露标题、所有者或变更元数据。
4. 覆盖共享父+私子、私有父、显式共享子、Call Log 间接链接和 Deal 原 Lead 历史路径；升级 CRM 后复核覆盖方法签名与返回结构。

M8 后续的只读源码审计又补充了以下旁路；它们是**源码证据，不是 M6 已完成的 HTTP 实证**，也应纳入同一扩展闭环：

- `get_data` / `set_activity_counts` 的未过滤 Note/Task 数量会泄露存在性和计数，必须按授权子 ID 重新计数。
- `get_call_log` 即使过滤 `_notes` / `_tasks`，原始 `note`、`links` 和引用字段仍可能泄露正文或候选 ID，必须同步清理。
- `FCRMNote.notify_mentions` 会把内容写入 CRM Notification；创建提及通知前必须逐收件人验证 Note read，不能向无权限者复制原文。
- `integrations.add_note/task_to_call_log` 对已有对象存在 `save(ignore_permissions=True)` 路径；白名单覆盖必须验证当前用户对已有 Note/Task 的 write 及父 Call Log 的相应权限，不能仅凭认证和对象 ID 更新。

Framework 的 `has_permission` 与 `DatabaseQuery.build_match_conditions` 都有 DocShare 补充逻辑。若扩展选择在 hook 内硬拒绝，hook、查询/auth filter 与 CSV 必须使用同一授权谓词，避免详情拒绝但列表/导出仍被另一条 DocShare OR 放行；read share 与 write share 必须分别测试。

这是必要的白名单 override，而不是修改核心。若不愿意承担该小范围升级复核成本，替代方案只能继续禁止使用私域 Note/Task，不能宣称它们已隔离。

### 6.3 Lead 分享列表与详情一致性

短期采用 Open ToDo 分配，不改核心。若产品要求“仅 DocShare 即出现在 Lead/Deal 列表”，需要在上游/受控分支调整 `crm.permissions.org_hierarchy` 的查询条件，把显式分享名称并入 owner/assigned 条件，并补 list/detail/export 一致性测试。

**不建议在扩展 app 再叠一个 Lead `permission_query_conditions` 试图放宽：** 多钩子的条件可能按 AND 组合，只会进一步收敛，不能可靠扩大原生可见范围。也不应通过猴子补丁替换 CRM 钩子。

### 6.4 Organization/Contact 边界

当前明确将二者定义为正式团队共享资料，私域入口只用 Lead。若未来确需私有 Organization/Contact，必须另做 owner/share 权限设计和关联回归，尤其 Contact 已有 Framework 自带权限钩子；不能简单加一条规则后假定组合顺序和链接字段行为安全，也不能把现有正式共享记录改成默认私有。

## 7. UI 视觉与后续验收

本轮 M6 是 HTTP/API 验收，**团队双账号浏览器视觉和 JavaScript 交互未测试**。M7 仅完成合成 System Manager 登录及 `/resource-import` 页面就绪，未做导入提交或完整视觉验收。tower 接管后在同一浏览器会话实际点击 preview 得到 HTTP 403；该 UI 结果未被 12 项 API 通过覆盖，仍为独立待定位失败。释放后未再改角色/禁用，M6 User Permission 仅作用于 FCRM Note；需根据脱敏响应区分 CSRF/旧页面会话与 authorize 拒绝。修复后至少用两个隔离浏览器上下文验证：

- 列表、全局搜索、仪表盘计数、最近记录、直接 URL、关联时间线和导出均无私域内容或数量侧漏。
- A/B 看到的共享记录可协作，私有 Note/Task 不出现在 DOM、JS 响应或网络面板。
- 新建私域记录、显式共享、取消/关闭分配后的即时可见性，以及普通成员新建共享父下备注的权限。
- CRM 升级和扩展启用后重复双账号 API 与 UI 回归；单账号登录绝不能替代这些检查。

后续独立安全 mission 还需完成 Task 专项 HTTP/CSV、activities 及其余旁路修复，并在修复后重复双账号 API 与 UI 回归。M6 的诊断、复现和修复边界交付可以完成，但产品团队权限门槛仍未通过。
