# L3 日程实现契约｜D010300

状态：2026-11-04，**Provisional／供实现，不是功能交付**。主控于此日期暂选方案 B，理由、备选、中置信与撤销条件见下节，作为实施前即时决策证据。依据 [D-007](DECISION_LOG.md#d-007自主推进至-l3以时间段日程而非日历视图验收) 的用户授权与 M22 固定源码调查。L1/L2 团队安全、普通账号正常 CRM 初始化、业务全链及恢复仍未验收；本契约不撤销这些门槛。本文不占用新决策编号；交 tower 由既有文档 owner 补 D-008 并独审，**决策日志落地前不得启动后续产品编码**。本文件不替代决策链。

## 1. 暂选、证据与退出

| 方案 | 取舍 |
|---|---|
| B：独立 `team_schedule` app／`Team Schedule` DocType（暂选） | 复用 Frappe 会话、CSRF、ORM、事务、迁移、备份；隔离 Event/Task 历史及副作用。需自建小规模 ACL、时间段页面、忙闲和导入；必须集成同一 CRM 导航，不是永久孤立入口。 |
| A：原生 Event + 定向扩展（保留备选） | 已有时间段、Desk 日周格；但终点可空、Public/参与者权限、Communication 内容复制、提醒及 Google 生命周期均需约束。只有隔离 spike 证实少量扩展能封住所有路径且体验可接受，才重新比较。 |
| C：外接排程服务／CalDAV（暂缓） | 可复用成熟 UI/同步，但新增服务、认证、敏感副本、凭据和恢复；当前没有必要，未获私人账号或外发授权。 |

置信度**中**：源码支持可实现性，尚无本 app 运行、权限或 UI 证据。M22 的固定依据为 Framework `v15.125.0`、CRM `36bd8859f2a6345a620477bc708d0546e8c3f08a`：
- [Event controller](https://github.com/frappe/frappe/blob/v15.125.0/frappe/desk/doctype/event/event.py)：参与者/公开详情语义、Communication 同步及按日期查询不等于脱敏忙闲。
- [Framework permissions](https://github.com/frappe/frappe/blob/v15.125.0/frappe/permissions.py) 与 [db_query](https://github.com/frappe/frappe/blob/v15.125.0/frappe/model/db_query.py)：普通权限后仍有 DocShare OR，不能仅用 `has_permission=False` 作为隔离证明。
- [依赖声明](https://github.com/frappe/frappe/blob/v15.125.0/pyproject.toml)：`pytz==2025.2`、`python-dateutil~=2.9.0`、`vobject~=0.9.7`；仅声明已核，运行版本/import/API **未证实**。先在隔离候选核验，不安装包掩盖缺失，不自行增加依赖。

若局部 ACL 无法安全覆盖标准入口、依赖不可用或导航成本超出小扩展，向 tower 提交证据并复评，不堆全局拦截。回退停止新写入和导航，保留 app/schema/权限、来源映射与取消墓碑；不 uninstall、不删历史、不撤安全 hook。备份后可经授权导出中立 UTC/时区/归属/来源数据；含 app 的兼容镜像才可回退。不得改现站 `Asia/Kolkata` 或重新解释旧 creation/modified。真实账号连接、邀请、外发、历史时区迁移另需授权；当前本地可逆选择无新增用户决策卡点。

## 2. 唯一数据与时间编码

所有新日程实际时刻采用 **Data(20) 固定宽度 `YYYY-MM-DDTHH:mm:00Z`**，秒只能 `00`，严格解析后重新编码比对，不接受 offset/naive/任意日期字符串。数据库不使用 Frappe Datetime 表达这些字段，比较为规范字符串或 aware UTC；不能交给原生系统时区转换器再解释。API/UI 显示时显式带 IANA 区域与 UTC offset。

| DocType（均 app 自有） | 权威字段／约束 |
|---|---|
| `Team Schedule` | `name` 随机不透明 ID；Framework `owner` 为创建会话用户、不可转让；`title`(140)、`description`(4000，纯文本)；`start_utc/end_utc`；`source_timezone` 已支持 IANA 名称；`status=Active/Cancelled`；`availability=Busy/Free`；`revision` 正整数初始 1。 |
| `Team Schedule Member`（子表） | `user` 唯一、启用的站内成员；`access=Read/Edit`；`occupies` 默认 false，仅该成员自行接受才 true。owner 总是占用主体；加入参与者不自动改排或占用他人。 |
| `Team Schedule Busy Grant` | `subject_user` 只能为会话自己，`viewer_user` 为明确启用成员；唯一有向对；允许对方查看自己的忙闲，不授予详情/edit。无团队默认公开。 |
| `Team Schedule Source` | `owner` 会话本人；随机 `name`、本地标签；不存 URL/凭据，不连接外部。 |
| `Team Schedule Source Item` | 唯一 `(source, uid)`；source 隐含 owner 域；指向 schedule（未知取消可为空）；`source_sequence`、`source_digest`、`last_import_revision`、`tombstone`；内部字段不在普通日程详情返回。UID 大小写敏感、最多 255 字符。 |

`start < end` 必填、精确到分钟、单次最长 31 天；不固定 30/60 分钟槽。`source_timezone` 是创建/导入时解释本地时刻的区域，不随查看者时区改变。修改时间必须同时提交三字段；不改变 owner。正文 HTML 按文本展示，不允许脚本、富文本执行或 URL 抓取。首版不加 CRM Link 字段：业务事项用显式成员共享即可，避免不可读父对象引用泄露；以后关联另定父权限交集契约，父可读绝不自动获得日程 edit。

本地输入仅由 `resolve_local` 转换：严格 IANA 白名单（运行 pytz 所含区域）、分钟字符串 `YYYY-MM-DDTHH:mm`，不存在的 DST 时间拒绝；双解必须提供候选中的 `offset_minutes`（当地减 UTC），禁止静默猜测。返回规范 UTC 与 offset 后再保存；服务端仍校验 UTC + 区域有效性。示例 `2026-11-04T17:37:00Z` 在上海为次日 01:37，在 Kolkata 为当日 23:07；不能改系统时区实现。

## 3. 权限与标准旁路

详情权限与忙闲权限独立；所有请求实时核验启用用户、成员身份及撤权，不复用浏览器缓存。

| 主体 | 详情／标准查询 | 修改时间、正文、Busy/Free／取消 | 成员 ACL | 忙闲 |
|---|---|---|---|---|
| owner | 读自己的全部（含取消） | 是，需 revision | 仅 owner 可设 Read/Edit/撤回；不能替成员接受占用 | 自己；其他人需对方 grant |
| 显式 Read 成员 | 读被授权记录 | 否 | 只能接受/撤回自身 `occupies` | 不因详情授权获得他人全部忙闲 |
| 显式 Edit 成员 | 读被授权记录 | 是，需 revision；不能改 owner/来源/ACL | 同 Read | 同 Read |
| 仅获得 busy grant 的人 | 无详情 | 否 | 无 | 仅授权主体的脱敏占用投影 |
| 其他普通账号／Guest | 无；不存在与无权统一响应 | 否 | 无 | 无 |
| Administrator／System Manager | 明示维护例外，可审计读取；不作为普通团队验收身份 | 走相同版本服务，不跳过校验 | 维护必须显式留安全元数据 | 无默认团队查询扩权 |

- `has_permission`、query conditions、controller 最终校验共享同一局部 ACL；子表读必须回查父权限。Source/Source Item 仅 owner/维护身份可读，禁止标准写入；Grant 仅涉及本人可见且只能本人授予/撤回。
- **不以 DocShare 表达授权**：普通用户无 Share 权限；只针对上述自有 DocType 的 DocShare 创建/更新，在 DocShare 定向生命周期校验拒绝（含管理员；管理员改用成员 ACL），不得影响其他类型。迁移先检查已有相关 DocShare，存在则中止开放入口并报告，不能删除或忽略。撤权必须同步清理/拒绝异常 share；验收证明 query hook 之外的 OR 无可利用行。此不变量不成立即阻断上线。
- 日程普通标准 REST GET/list 可按 ACL 读；直接 REST PUT/POST/DELETE、bulk、`client.set_value` 等写入一律由 controller 拒绝，唯一写通道为下节版本服务。服务内部用不可由 HTTP 设置的调用上下文，不接受客户端 `flags` 绕过。无硬删除 API。所有 owner/ACL/来源/内部字段白名单校验，未知写字段拒绝。
- 禁用自有类型的普通 Export/Print/Email/Report/Import 权限；只开放受控 `export_owned`，不把禁用按钮当服务端保护。标准详情/list/reportview/search/link/docinfo、两种 CSV exporter、子表、Version、附件、实时与共享仍须负测。查询不能返回未授权 name/count/摘要，聚合也按 ACL。
- 自有类型不建全文索引，不向 Communication/ToDo/Notification/邮件/实时广播复制标题正文；不启用全文 Version，操作审计仅 actor、时间、动作、ID、revision，不存正文/UID。页面和日志均不回显私密异常上下文。不得用 `ignore_permissions`、任意 SQL API、全局 `before_request`/SQL/响应拦截替代这些局部设计。

## 4. API（冻结命名与边界）

入口 `/api/method/team_schedule.api.<method>`；源导入入口 `team_schedule.ics.api.<method>`；忙闲入口 `team_schedule.availability.api.<method>`。Frappe 返回外层 `message`，以下指其内部 JSON。标准会话、启用用户、写 POST + CSRF，均同源 `Cache-Control: no-store`。列表和导出不通过 GET query 携带正文。未知参数拒绝。

| method | 参数 | 返回／行为 |
|---|---|---|
| `resolve_local` POST | `{local, timezone, offset_minutes?}` | `{utc, timezone, offset_minutes}`；双解返回 `AMBIGUOUS_LOCAL_TIME` 及仅两个 offset 候选，不保存。 |
| `create` POST | `{title,description,start_utc,end_utc,source_timezone,availability,members:[{user,access}],request_id}` | `{schedule:Detail}`；request_id UUID 按会话用户持久幂等，相同 key 不同 payload 拒绝，重复同 payload 返回同结果。 |
| `get` POST | `{name}` | `{schedule:Detail}`。 |
| `list` POST | `{start_utc,end_utc,include_cancelled:false,cursor:null,limit:100}` | `{items:[Detail],next_cursor:null|string}`；交集 `start < window_end AND end > window_start`，稳定按 start/name；limit 1..100，窗口最长31天。cursor 绑定用户/过滤器，不接受任意 SQL。 |
| `update` POST | `{name,expected_revision,changes}` | `{schedule:Detail}`；changes 只允许正文、完整时间三元组、availability；取消后拒绝普通编辑。 |
| `set_members` POST | `{name,expected_revision,members:[{user,access}]}` | `{schedule:Detail}`；仅 owner，不能把已有 false 变 true；移除立即失效，占用同撤回。 |
| `set_participation` POST | `{name,expected_revision,occupies:boolean}` | `{schedule:Detail}`；仅自己的现存成员行。 |
| `cancel` POST | `{name,expected_revision}` | `{schedule:Detail}`；Active→Cancelled 增 revision，已取消且 revision 相同则 no-op；不发送通知/取消他人其他安排。 |
| `set_busy_grant` POST | `{viewer_user,allow:boolean}` | `{viewer_user,allow}`；subject 恒会话本人，授予/撤回幂等；撤回即时生效。 |
| `export_owned` POST | `{start_utc,end_utc}` | 私密下载 JSON（非公开 File），仅本人拥有、最多31天/1000条，超限失败；含完整时间、内容、成员、授权来源映射/墓碑以支持迁移，不导出他人的详情或 grant；不得记录正文。 |

`Detail` 精确字段：`{name,owner,title,description,start_utc,end_utc,source_timezone,status,availability,revision,members:[{user,access,occupies}]}`，无 source/UID/hash/内部标记。每次成功变更原子加 revision（含 ACL/参与变更）。使用行锁并比较 expected_revision，验证与提交同事务；冲突 `409 REVISION_CONFLICT` 不返回他人的当前正文，客户端重新有权读取再决定。

B 同时拥有内部 `Team Schedule Request` schema：唯一 `(owner,request_id)`、规范payload完整SHA256、schedule ID；不存正文快照，禁止普通标准读写/分享，仅服务按会话本人查。创建幂等记录及日程同事务；超时以相同 create 参数/key 重试（即回查），重验身份权限后返回同ID的当前 Detail，不盲目另建。ICS receipt 使用现有 Redis 临时存哈希计划/目标版本而非正文，丢失或过期重新预览；不新增持久 receipt schema。上述内部类型同受局部 DocShare 拒绝及不索引/广播约束。

安全错误 `{error:{code}}`：400 `INVALID_INPUT`，401 `AUTH_REQUIRED`，403 `FORBIDDEN`，404 `NOT_FOUND`（ID 不存在/无权同码），409 `REVISION_CONFLICT/IDEMPOTENCY_CONFLICT`，413 `LIMIT_EXCEEDED`。不含堆栈/路径/候选私文；底层会话错误沿站点已配置安全错误策略验证，不为此新增全局拦截。撤权或身份错误页面清空已加载业务数据和草稿，无 localStorage/IndexedDB/service-worker 业务缓存。

### 忙闲与共同空闲

`availability.api.query` POST `{users:[user],start_utc,end_utc,min_minutes:20,display_timezone}` → `{busy:[{user,intervals:[{start_utc,end_utc}]}],common_free:[{start_utc,end_utc}],display_timezone}`。users 去重后 1..10 人、必须包含自己；除自己外逐人需要有效有向 grant，任一失败整请求 403，不指出哪个用户存在/拒绝原因。窗口最长7天，min_minutes 为 1..10080 整数；同源会话每分钟最多30次。`display_timezone` 仅显示元数据，权威区间仍 UTC。

仅 Active+Busy，按 owner 或 `occupies=true` 成员计入该人的占用；Free/Cancelled 不占用。查询使用 **[start,end)**，先裁剪窗口，按人合并重叠/相邻，再求所有人 busy 并集在窗口的补集，最后按分钟长度过滤；相邻不冲突。返回不得含 event ID/name、标题、正文、成员列表、关联、UID、来源或计数。最多扫描10000条占用记录，超限/未完整扫描报413，绝不返回假空闲；在一致性读视图计算。

保存不自动改排或取消；UI 保存前用有权 busy 查询提示交叠并让用户确认继续，提示只是查询时快照不是预订锁；无权查询者不能从保存错误推断他人占用。保存时段列表必须标出具体起止，不能用月历格或 Task deadline 冒充安排。

## 5. 合成 ICS 单向预览→确认导入

只接受用户本地 UTF-8 文件（可 BOM），≤1MiB、≤200个 VEVENT、单 UID 不重复；不抓 URL、不读私人账号、不执行附件/邀请/提醒。先核验 vobject 实际可用，再解析并做业务白名单校验；解析成功不等于支持完整 RFC5545。

- 支持单 VCALENDAR、VERSION:2.0、PRODID、METHOD:PUBLISH/CANCEL（可省略 METHOD）；VEVENT：UID、非负 SEQUENCE（省略为0）、DTSTAMP/LAST-MODIFIED（可省略；仅 UTC 元数据，不决定版本）、SUMMARY/DESCRIPTION、TRANSP:OPAQUE/TRANSPARENT（省略 Busy）、STATUS:CONFIRMED/TENTATIVE/CANCELLED（前两者均 Active）。保留折行与转义语义后的文本。
- 活动项必须 DTSTART+DTEND，UTC `Z` 或 `TZID=<已支持IANA>`；秒必须00；Z 输入 source_timezone=UTC，TZID输入用对应区域。DST 双解/不存在一律逐项拒绝，不从机器时区猜测；不接受自定义 VTIMEZONE，即使名称像 IANA。
- 明确拒绝 VALUE=DATE 全天、浮动时间、数字offset时间、DURATION、RRULE/RDATE/EXDATE/RECURRENCE-ID、VALARM、VTODO、ATTACH、URL、ATTENDEE、ORGANIZER、任意 VTIMEZONE、未知属性/组件/参数（允许支持属性上的合法 TZID/VALUE=DATE-TIME，以及 DESCRIPTION/SUMMARY 的 LANGUAGE）。不静默删掉重复规则、邀请或未知字段当成功；容器/编码损坏拒整文件，可定位的坏 VEVENT 逐项报安全错误，其余可预览。
- METHOD:CANCEL 或 STATUS:CANCELLED 都只作取消；取消项允许省略时间/正文，但必须 UID+SEQUENCE，若提供时间仍须合法。新来源的未知 UID 取消建立**仅映射墓碑**（无日程/占用），结果 `unknown_cancelled`，防随后旧文件复活；不泄露其他来源同 UID 是否存在。

`ics.api.create_source` POST `{label}` → `{source_id}`；owner 不可传入。`preview` POST `{source_id,file_base64}` → `{receipt,expires_in:900,items:[{index,action,code,preview?}]}`；preview 仅自身输入解析内容与有权目标，业务表零写，临时 receipt 不存原文件/正文。`apply` POST `{receipt,source_id,file_base64,confirm:true,resolutions:[]}` → `{items:[{index,result,code,schedule_name?,revision?}]}`。源仅本人可用；无权 source 返回同404。全文件哈希、用户、会话、source、规范计划、预览时目标 revision/源版本、resolutions 白名单绑定15分钟不透明 receipt；apply 再解析并重验，换文件/会话/权限/版本失败，不接受客户端替换计划。

版本与本地编辑规则（同源 UID；SEQUENCE 为唯一有序版本，时间戳不打破平局）：

| 输入与已存来源版本 | 处理 |
|---|---|
| 首次活动 | 创建日程，仅 owner，无外部参与者；映射唯一约束与日程同事务。 |
| 同 sequence、同规范 digest | `duplicate` no-op，即使日程后来本地改过也不覆盖。digest 为支持字段规范 JSON 的完整 SHA256（排序、UTC、规范文本、取消态）；不含折行、PRODID、DTSTAMP/LAST-MODIFIED。 |
| 低 sequence | `stale`，不写。 |
| 同 sequence、不同 digest | `version_conflict`，不提供强行覆盖；需修正源版本后重新预览。 |
| 高 sequence、当前 revision=last_import_revision | 更新/取消并记录新 source sequence/digest 与新 revision。 |
| 高 sequence、本地 revision已变 | `local_conflict`；默认不写。只允许预览中 owner 显式选择 `replace_from_source`，二次确认绑定目标 revision；覆盖源管理的时间/正文/availability/status，不改本地成员 ACL。 |
| 已有 tombstone 后任何活动项 | sequence ≤墓碑拒绝复活；更高也返回 `cancelled_source`，首版不自动恢复，需新 UID。重复取消幂等，高版本取消可前移墓碑。 |

正常成员 ACL/参与状态变更也算本地 revision 变化，宁可提示冲突不静默覆盖。每项保存点、同 source+UID 事务锁及唯一约束；锁到 commit 后释放，失败回滚该项及其映射，其他成功项保留。确认前后发生竞态返回该项 `revision_conflict`，不能用旧确认覆盖；重新预览确认。receipt 有效期内可重试，同版本成功项 no-op、失败项重试；过期重新预览。来源版本和取消墓碑纳入备份恢复。响应仅 index、分类、安全 ID，不将解析器异常/源私文写日志；失败下载纯文本安全编码，不执行 HTML/表格公式。

## 6. 文件 ownership 与实现顺序

下表是后继任务排他边界，不代表这些目录已存在。协调顺序：后端 B 冻结 DTO/ACL与 schema → F/I 并行 → U/N → D 单一集成。共享文件仅一个 owner，其他 worker 用 tower 请求变更，不能各自编辑 hooks/schema。

| owner | 唯一可写范围（相对仓库根） | 必须交付的测试契约 |
|---|---|---|
| B 后端/权限 | `apps/team_schedule/` 包骨架、清单、`team_schedule/hooks.py`、`modules.txt`、全部 `doctype/**`（含 source/grant 子表）、`patches/**`、`patches.txt`、`api.py`、`service.py`、`permissions.py`、`timeutils.py`、`tests/test_model*.py`、`tests/test_permissions*.py` | 版本行锁、创建幂等、严格时间与DST、标准入口/DocShare负测；为I提供 source item事务访问接口。B唯一注册各模块 hooks，禁其他worker改schema。 |
| F 忙闲 | `apps/team_schedule/team_schedule/availability/**`、`tests/test_availability*.py` | grant、裁剪/合并/补集、边界相邻、超限失败；只调用B ACL/时间接口，不回传详情。 |
| I ICS | `apps/team_schedule/team_schedule/ics/**`、`tests/test_ics*.py`、`tests/fixtures/ics/**` | 支持/拒绝矩阵、来源隔离、版本/墓碑/本地冲突、逐项恢复/双并发；不自行创建 DocType或安装依赖。 |
| U 页面 | `apps/team_schedule/team_schedule/www/**`、`public/**`、`tests/ui/**` | 标准会话/CSRF/no-store、分钟时间段CRUD、导入双确认与撤权清屏；所有脚本只用本契约API。 |
| N CRM导航 | `frontend-patches/l3-scheduling/**` | 核定固定CRM真实侧栏位置后精确patch；同源 `/team-schedule` 可达并返回CRM，不改 `c011000` 身份门禁/main.js，不重写全局路由。 |
| D 部署/验收 | `deploy/**`、独立验收材料 `docs/qa/l3-*`（由tower明确分配） | 单一镜像加入app+导航资产、依赖核验、两次迁移、双普通账号正常CRM UI、重启/备份恢复/兼容回退；不把后台www页面测试代替正常产品入口。 |
| M23 契约 | 仅本文件 | 静态一致性与任务对照；不声明任何功能已通过。 |

实现使用项目现有测试框架/约定，模块测试由各owner维护；D负责真实 Frappe 集成和浏览器证据，不以 mock/import/compile 取代 HTTP/页面验收。不新增复杂排班、自动调度、双向同步、外发或完整 RFC5545。

## 7. 必过验收（合成数据，证据逐项记录，均尚待执行）

1. 两名普通成员正常 `/login`→CRM（保留既有身份初始化门禁）→侧栏日程→创建/改/取消→返回商机；显示 09:07–09:42、13:03–13:18 和 23:57–次日00:11，分钟输入、日内多段/跨日、开始/结束/时区/忙闲/取消态清晰。零/负时长、缺终点拒绝；API/UI/重启恢复一致。
2. 上海/Kolkata 同一UTC跨日期；纽约 `2026-03-08 02:30` 不存在拒绝、`2026-11-01 01:30` 双解要求 offset；ICS 双解拒绝。原站系统时区与旧数据不变。
3. 共同窗口09:00–14:00：A busy 09:07–09:42、13:03–13:18；B busy09:30–10:05、13:18–13:31；min20仅得10:05–13:03和13:31–14:00。验证相邻无冲突、Free不占用、取消/移时更新、跨日裁剪、全忙/全闲、重复参与、未接受成员不占用、撤grant及扫描超限不返回假空闲。
4. A私事标题/正文放唯一canary，B在UI/REST detail/PUT、list/reportview、搜索/link、docinfo、子表、两CSV导出、print/email/report、Version/实时及忙闲都不能拿到canary/源UID；仅授权busy时段可见。Read不能写、Edit不能改ACL/owner/source；撤成员、禁账号、并发旧revision、伪造flags/owner/source、DocShare OR路径逐项证实拒绝。管理员烟测不能替代。
5. ICS首次、折行等价重复、高/低版本、等版异文、取消/重复取消/未知取消墓碑、旧文件不复活、不同源/用户同UID、本地改后冲突与显式覆盖；Z/TZID、坏UTF-8/缺UID/坏时间/不支持属性/超限/恶意HTML；混合好坏项、注入单项写失败、双并发、预览后换文件/会话/撤权/改revision、过期重试。成功项保留、失败不留孤儿、无邀请/提醒/外部请求。
6. 单一集成候选真实依赖版本/import、构建、两次迁移；重启持久化、数据库及私有文件备份到隔离站点恢复，再读详情/来源/墓碑/grant；受控导出及含app兼容回退。L1/L2安全与CRM业务全链仍须单独收敛，未通过不得称完整L3。
