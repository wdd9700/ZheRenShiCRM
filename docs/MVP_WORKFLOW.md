# MVP 业务闭环：资源导入 → 企业/联系人 → 需求 → 商机 → 沟通 → 下次跟进 → 时间线

**状态（2026-10-31 收口）：M5 的交付是「原生导入能力实测 + 合成样例 + 业务工作流演示/操作文档」，不是完整 MVP。六列网页导入已正式拆给 M7（`resource_import`，目前仍在部署测试，**未验收**）；完整 MVP 还需 M6 的权限修复结论与视觉验收。M5 的脚本只允许合成数据验证。**

- 实例：`crm-mvp-v15`，站点 `crm.localhost`，入口 `http://127.0.0.1:8088/crm`（仅回环，合成数据）。
- 版本：Frappe Framework `15.125.0`，Frappe CRM `1.90.0`（`deploy/README.md` 已锁定的派生镜像）。
- 记录原则：只写**实际执行过**的结果；第 2–5 节是**本轮历史实验记录**（真实执行、仅合成数据、发生在 M6 安全结论之前），第 6–9 节是收口后的边界与更正。

## 0. 交付边界与安全门槛（收口结论）

| 项 | 结论 |
|---|---|
| 六列网页导入 | **不属于 M5**，已拆给 M7；M5 不提供 UI，不声称可用 |
| M5 脚本用途 | 仅合成数据验证/参考实现；生产导入入口是 M7 |
| 合成数据防护 | `tools/crm/m5_guard.py`：①`preview`/`apply` 都只接受与仓库固定样例**完全一致**的归一化 SHA-256（摘要写死、不接受自报哈希）；②行级企业名以 `M5`、姓名以 `样例` 开头。无旁路开关；本地回归 `python tools/crm/selftest_guard.py`（含"合法前缀 + 真实样式载荷必须拒绝"） |
| 安全前提（M6） | 两个真实 Sales User 的 HTTP 请求证实：FCRM Note 私密 detail/PUT 均返回 **200**（跨用户越权读取与改写），activities 也会返回未共享的 note。因此**联系方式原文/需求原文不得靠 FCRM Note 承载真实资料**，也解释了为什么 M5 旧路径只能跑合成数据 |
| 完整 MVP 定义 | M7 网页导入 + M6 权限修复 + 视觉验收 + 备份恢复演练，缺一不可 |
| 共享实例状态 | 现由 M7 独占部署；M5 不再对其执行写库或 HTTP 操作 |

## 1. 结论速览（历史实验结论，均在合成数据上真实执行）

| 能力 | 结果 | 证据 |
|---|---|---|
| 原生导入入口 | `/crm/data-import`、`/crm/data-import/doctype/:doctype`，v15 回落 framework 经典向导（上传→映射→预览→导入） | 前端源码 + SPA 路由 200 |
| 原生列映射 | 可用，但中文表头**不自动匹配**，必须人工按列映射（映射键是列序号，不是表头） | 预览 warnings 逐列 `Cannot match column 姓名/公司名称/…` |
| 原生"开始导入" | **原部署被调度器禁用挡住；受控开启后真实跑通** | 开启前 `ValidationError: Scheduler is inactive. Cannot import data.`；开启后 `start_import()`→`True`→状态 `Partial Success` |
| 原生逐行错误 | 可用（`Data Import Log` 每行一条，含异常正文） | 缺姓名行 `Error: Value missing for CRM Lead: First Name`；含微信/邮箱原文行 `… is not a valid Phone Number` |
| 原生重复控制 | **没有**自然键去重，同一文件导两次记录翻倍 | 同一 3 行文件走两次 UI 路径 → `CRM-LEAD-2026-00012` 与 `-00013` 同姓名同手机号 |
| 一次导入建企业+联系人+需求 | **不支持**（一次一个 DocType） | `Data Import.reference_doctype` 单值 |
| 六列里的"需求/产品"列落到 Lead | **无原生字段** | `CRM Lead` 元数据里没有需求文本字段 |
| 参考适配脚本（合成数据） | 已跑通、可重复执行不重复建记录；**已被 M7 取代，不作生产入口** | `tools/crm/m5_import.py`：首次 2 企业/3 联系人/4 需求；二次 0 新增 |
| 需求→商机 | 原生人工转换（`convert_to_deal`），脚本**不会**自动建商机 | `CRM-DEAL-2026-00001`、`CRM-DEAL-2026-00002` |
| 沟通/跟进/阶段/时间线 | 已跑通 | 4 条评论、2 个 `CRM Task`、阶段日志、时间线接口 7 条活动 |
| 可视 UI 点击验收 | **未做** | 内置浏览器 `browser.create_tab` 返回 `BROWSER_UNAVAILABLE`；后续由 tower 协调 |

## 2. 原生导入实测（含调度器，历史记录）

### 2.1 开启调度器前的受控核对（2026-10-31 02:05，只读）

| 检查项 | 结果 |
|---|---|
| 现成收件人/邮件通道 | `Email Account` **0 条**（无任何外发账号）、`Email Queue` 0 条、`Communication` 已发送 0 条、`Newsletter` 0 条 |
| 自动通知/报表 | 启用的 `Notification` 0 条、`Auto Email Report` 0 条 |
| 外部集成 | `Webhook` 0 条；`Google Settings.enable=0`；Microsoft 设置模块不存在；`Lead Sync Source` **0 条**（含启用的 0 条） |
| 遥测 | Frappe pulse `is_pulse_enabled()=false` → `crm.telemetry.capture_feature_state` 直接返回 |
| 队列 | 所有 `rq:queue:*` 长度 0，`started/failed` 注册表 0 |
| 用户 | 仅 `Administrator` 一个启用账号 |
| 域名补全 | `auto_enrich` 默认关；本轮所有记录都没有 `website`，不会触发抓取 |

结论：没有真实收件人、没有外部同步源、没有外发通道，条件满足后才启用。

**变更与回退**：`System Settings.enable_scheduler` 原值 `0`；执行 `bench --site crm.localhost enable-scheduler`（只改该站点，不动 Docker/系统服务，不清队列）后为 `1`。回退命令：`bench --site crm.localhost disable-scheduler`。

遗留说明（未改配置，仅记录）：`change_log.check_for_update` 与 `changelog_feed.fetch_changelog_feed` 是 Weekly Long 的**应用更新元数据**检查（会访问上游站点，但不含任何业务数据），首次 `last_execution` 为空、本次核对时尚未执行；`google_*`/`email_account.*` 因无配置为 no-op。若要求零外联，需要另行决定是否停用这两条 Scheduled Job Type。

### 2.2 开启后真实原生导入（走 UI 同一路径）

3 行合成 CSV（唯一前缀 `M5UI`）：`UI-1` 正常行、`UI-2` 缺姓名、`UI-3` 联系方式写成 `13700000003 / 邮箱 m5.ui.c@example.com`。

```
start_import()            → True（真正入队，不再绕过调度器）
后台 worker 处理完成       → Data Import.status = Partial Success
row 2 → 成功  CRM-LEAD-2026-00012
row 3 → 失败  Error: Value missing for CRM Lead: First Name
row 4 → 失败  13700000003 / 邮箱 m5.ui.c@example.com is not a valid Phone Number
```

同一文件第二次走同一路径 → 新建 `CRM-LEAD-2026-00013`（与 -00012 同姓名、同手机号），`M5UI` 线索变 2 条。**原生没有自然键去重**，这不是配置问题，是 `Importer.insert_record` 永远新建的实现事实（`Update Existing Records` 模式才按 `name`/autoname 字段更新）。

导入后副作用核对：`Email Queue` 仍 0、`Communication` 0、`Webhook` 0、`Notification` 0；`ToDo` 8 条（内部指派，无外发）。

### 2.3 原生能力的边界（决定为什么要适配层）

- 中文表头 → 字段映射要人工做，且每次新导入都要重做（除非保存 `template_options`）。
- "需要的产品、服务""公司产品、服务"在 `CRM Lead` 上**没有任何字段可映射**。
- 手机号列必须已是合法号码；把"手机 / 微信 / 邮箱"原文塞进去会被 Phone 校验拒绝。
- 一条 CSV 只能建一种 DocType：企业、联系人、需求必须分别导入，且它们之间的关系（Lead→Organization 是 Data 文本，Deal→Organization 才是 Link）不会自动建立。
- 没有去重/幂等，重复导入直接翻倍。

## 3. 参考适配脚本：`tools/crm/m5_import.py`（历史合成工具；已被 M7 取代）

容器内运行，Python 标准库 + 已安装的 frappe，无新依赖、无自定义字段、无数据库结构变更。

**写入闸门（R1 修复后）**：`apply` 与 `preview` 都先过 `m5_guard.require_trusted_sample()`：

1. 文件内容必须与仓库固定合成样例 `samples/m5-synthetic-six-columns.csv` 的**归一化 SHA-256 摘要**
   完全一致（摘要写死在 `m5_guard.TRUSTED_SAMPLES`，**不接受调用方自报的任何哈希**）；
2. 行级再校验企业名以 `M5`、姓名以 `样例` 开头。

因此改过联系方式/产品/需求/来源的文件一律被拒；`preview` 额外打印"仅解析演示、不是真实数据路径"。
`apply` 仍在 `--confirm` 后写库，且**每行**都调用 `ensure_source()`（R1 P2 修复：原先在循环前插入 Source
但未提交，首行失败回滚会连带回滚 Source，导致后续行级联失败）。

```
preview  只读，输出逐行计划与错误，退出码 0（无错误）/2（有错误行）/1（致命或非可信输入）
apply    真实写入，必须带 --confirm；退出码同上
```

| CSV 列 | 去向 | 去重/幂等方式 |
|---|---|---|
| 序号 | 写进来源备注，不当业务主键 | — |
| 姓名 | `Contact.first_name`（脚本命名如 `样例张一-M5样例企业甲 智能制造`） | 手机号 → 邮箱 → 姓名+企业，三级匹配 |
| 公司名称 | `CRM Organization`（docname 即企业名） | 同名即复用 |
| 联系方式 | 原文写入联系人 `FCRM Note`；解析出的手机号/邮箱写入 `phone_nos`/`email_ids` | 手机号按数字归一后匹配 |
| 公司产品、服务 | `CRM Organization.company_description` | 复用时只读不覆盖 |
| 需要的产品、服务 | **每条需求一条 `CRM Lead`**（`status=New`，`source=M5导入样例`）+ `FCRM Note` 保存需求原文 | 导入键 = SHA1(企业｜姓名｜手机号或邮箱｜需求原文) **前 16 位**（历史算法，保持不动），写入备注 HTML 注释 `<!-- m5-import-key:… -->`，重跑按此跳过 |

**幂等键说明（R1 P2 更正）**：代码始终是 16 位截短 SHA1，**没有**改成 40 位；改长度会让
`find_lead()` 找不到旧备注并重插需求，所以刻意保持不变。它不是生产方案（碰撞面、依赖文本检索）——
生产幂等由 M7 用唯一字段 + **完整 SHA-256** 实现。

补充规则：

- **不创建商机**；升级必须人工（UI 或显式调用 `convert_to_deal`）。
- **联系方式原文不丢**：原文（含"微信 m5-demo-a"这类不可解析片段）与来源文件/行号/序号写进 `FCRM Note`；只在联系人新建时写，避免重复行堆备注。
- **错误行按行报告、不中断**：缺姓名/缺企业/缺需求/联系方式无法识别都单独列为失败行。
- **只增不删**：没有删除路径，也不改已有记录的业务字段。

实测（真实库，`samples/m5-synthetic-six-columns.csv` 8 行）：

```
行  序号      企业                        联系人                  需求
2   M5-001   新建:M5样例企业甲 智能制造    新建:样例张一           需求新建
3   M5-002   复用:M5样例企业甲 智能制造    新建:样例李二           需求新建
4   M5-003   新建:M5样例企业乙 食品加工    新建:样例王三           需求新建
5   M5-004   复用:M5样例企业甲 智能制造    复用(手机号):样例张一    需求新建
6   M5-005   复用:M5样例企业乙 食品加工    复用(手机号):样例王三    需求文件内重复
7   M5-006   错误                        -                      缺少姓名
8   M5-007   错误                        样例赵六                缺少公司名称
9   M5-008   错误                        样例钱七                联系方式无法识别（无手机号或邮箱）…
计划汇总：企业=2，联系人=3，需求=4，需求跳过=1，错误行=3
```

二次执行：`企业=0，联系人=0，需求=0，需求跳过=5，错误行=3`，库中仍是 2 企业 / 3 联系人 / 4 需求 —— 幂等成立。

## 4. 业务闭环演示：`tools/crm/m5_workflow_demo.py`（历史记录，仅合成数据）

`--confirm` 才写库，缺省只读检查；重复执行不会重复建商机/评论/任务/阶段变更。

**写目标来源校验（R1 修复后）**：不再用"名字前缀"或"按 first_name 猜"定位记录，而是逐项核验受控样例身份与关系：

- Lead：按历史 16 位导入键（`m5-import-key:` 注释）定位，并核对 `organization` / `first_name` / `mobile_no` 与样例完全一致；
- Contact：按 `Contact Phone` 精确手机号定位，且必须同时满足 `first_name`、`company_name` 与 `links`（Dynamic Link → 该企业）；不唯一即拒绝；
- Deal：复用前核对 `lead` 与 `organization`；不匹配即中止；
- Task：只按 `reference_docname == 已验证商机` 复用，不做标题猜测。

任一校验失败都会输出原因并退出，不做写入。

| 对象 | 真实结果 |
|---|---|
| 企业 | `M5样例企业甲 智能制造`（工业机器人集成）、`M5样例企业乙 食品加工`（食品代工与仓储） |
| 联系人 | 样例张一、样例李二（企业甲）、样例王三（企业乙），均挂企业 Dynamic Link |
| 需求线索 | `CRM-LEAD-2026-00006`（质检数字化，已转商机）、`-00007`（产线排程）、`-00008`（冷链温控，已转商机）、`-00009`（售后工单知识库） |
| 商机 | `CRM-DEAL-2026-00001` 甲/质检 `Negotiation` 12 万 预计 2026-12-15；`CRM-DEAL-2026-00002` 乙/冷链 `Proposal/Quotation` 8.6 万 预计 2026-11-30 |
| 沟通事件 | 4 条评论（商机 A 电话沟通+现场拜访、商机 B 微信沟通、需求线索 B 电话初访），进入时间线 |
| 下次跟进 | `CRM Task` #1（2026-11-03 10:00 High，挂商机 A）、#2（2026-11-05 15:00 Medium，挂商机 B），状态 `Todo` |
| 阶段演进 | A：Qualification → Demo/Making → Negotiation；B：Qualification → Proposal/Quotation。`status_change_log` 记录 from/to/from_date/to_date/duration，`Version` 保留每次变更 |
| 时间线 | `crm.api.activities.get_activities` 每个商机返回 7 条活动：creation×2、changed、added、comment×2、note |

关系与查询验证：

- 按企业查：甲 → 商机 1、联系人 2、需求线索 3；乙 → 商机 1、联系人 1、需求线索 1。
- 按手机号 `13800000001` 查：2 条需求线索（同一个人的两个不同需求），互不覆盖。
- 商机详情同时有 `organization`（Link）、`lead`（Link）、`contacts` 子表、`next_step`、金额与预计成交日。
- 联系人职位改为"生产经理"已落库（查询修改路径）；Lead 转商机后 `converted=1`、状态 `Qualified`（CRM 原生行为，不是 `Converted` 状态）。

已知原生行为（记录以免误判为缺陷）：

- 商机 `probability` 只在创建时按阶段默认值写入，之后改阶段**不会**自动重算（演示里显示 10%，对应 `Qualification`）。
- 时间线会把连续的同字段变更折叠显示；完整历史在 `status_change_log` 与 `Version`。
- 演示脚本第一版 `shift_status` 在重复执行时会把已推进的阶段**回退再前进**，所以 `CRM-DEAL-2026-00001` 的阶段日志里留有 1 次 `Negotiation → Demo/Making` 回退。脚本已改为只前进，回退记录按审计原则**保留未删**。

## 5. 可复现路径（历史记录；共享实例现由 M7 独占，勿直接执行）

### 5.1 合成数据的命令行路径（需要 tower 给窗口）

主 checkout（合并后）在第一 Ubuntu 中执行；**共享实例现由 M7 独占部署，本组命令不得自行运行**，需要真实回归时向 tower 申请窗口：

```sh
cd /mnt/p/CRM
docker exec crm-mvp-v15-backend-1 mkdir -p /tmp/m5
docker cp tools/crm/m5_import.py crm-mvp-v15-backend-1:/tmp/m5/
docker cp tools/crm/m5_guard.py crm-mvp-v15-backend-1:/tmp/m5/
docker cp tools/crm/m5_workflow_demo.py crm-mvp-v15-backend-1:/tmp/m5/
docker cp samples/m5-synthetic-six-columns.csv crm-mvp-v15-backend-1:/tmp/m5/
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 \
  ../env/bin/python /tmp/m5/m5_import.py preview --csv /tmp/m5/m5-synthetic-six-columns.csv
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 \
  ../env/bin/python /tmp/m5/m5_import.py apply --csv /tmp/m5/m5-synthetic-six-columns.csv --confirm
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 \
  ../env/bin/python /tmp/m5/m5_workflow_demo.py --confirm
```

`/tmp/m5` 只是容器内临时目录，不进入镜像；脚本不读 `.env`、不打印密码。企业名不以 `M5` 开头或姓名不以 `样例` 开头的输入会被 `m5_guard.py` 直接拒绝。

### 5.2 CRM 界面（原生路径，历史核对）

浏览器打开 `http://127.0.0.1:8088/crm`（Administrator）：

1. **Leads** 列表看 4 条 `M5样例*` 需求线索；详情 Activity 有导入备注（需求原文、企业提供、联系方式原文、来源行）与评论；状态可改。
2. **Deals** 列表看 2 条商机；`CRM-DEAL-2026-00001` 详情可改 `Status`/`Next Step`/金额/预计成交日，Activity 显示创建、阶段变更、评论，Tasks 显示 2026-11-03 跟进。
3. **Organizations / Contacts** 看企业主营与联系人的手机/邮箱/关联企业。
4. **需求转商机**：在需求线索页用原生"转换为商机"（人工动作）。
5. **导入**：`/crm/data-import` 上传 CSV → 人工映射列 → 预览 → 开始导入（调度器已开启时可用），逐行结果在 `Data Import Log`。注意：这条原生路径仍**没有**自然键去重，不适合作为六列生产入口。

HTTP 级核对（历史）：上述路由返回 200 SPA 外壳与资产，`frappe.client.get_list`、`crm.api.activities.get_activities`、`get_preview_from_template`、`form_start_import` 均返回真实结果。

**未做且未声称**：浏览器可视点击验收（内置浏览器 `BROWSER_UNAVAILABLE`），以及六列网页导入（属 M7）。

## 6. 六列网页导入：已转交 M7（方案存档，未验收，非 M5 交付）

tower 最终决定：六列网页导入与服务端安全写入**独立移交 M7（`resource_import`）**；M5 不再实现 UI。本节保留的是交接方案存档，**M7 当前仍在部署测试，不能称为已验收**。

已否决的做法（保留为历史，不再推荐）：

- **浏览器逐条 `get_list`/`insert`**：并发幂等、失败原子性、权限、映射一致性都无法保证，**已否决**。
- **截短 SHA1 + 备注文本匹配做幂等**：碰撞面大、依赖文本检索、与 M6 揭示的 note 越权问题叠加，**只能作为历史合成演示**（代码保持 16 位未升级，以免旧合成数据重跑重插），不得作生产实现；生产幂等由 M7 用唯一字段 + 完整 SHA-256。
- **`uninstall-app` / 删除 Custom Field 作为回退**：会丢数据/丢审计，**不作为回退建议**；回退必须靠备份恢复 + 停用入口（见 6.7）。

以下 6.1–6.6 是对 M7 的技术输入（机制核验、目录、事务、权限、schema），不是 M5 的实施承诺。

本章只是实现交接方案，**未写任何 app、未改共享实例**。

### 6.1 加载机制核验（本部署只读实测）

| 事实 | 证据 / 结论 |
|---|---|
| `/crm` 本身就是 app 的 www 页 | `apps/crm/crm/www/crm.html` + `crm.py`（`no_cache = 1`，`get_context()` 里 `check_app_permission()`）→ **app 的 `www/` 页在本站点确实会被服务**；`/m5-import` 用同一机制即可，不依赖未验证的 Desk Page `page_html`，也不用 Server Script（`server_script_enabled` 默认关） |
| `sys.path` 是逐个 app：`env/site-packages` + `apps/crm` + `apps/frappe`（**不含 apps 父目录**） | 新 app 必须 `pip install -e` 进 env；运行中的 gunicorn/RQ 进程启动时已定 sys.path，**改 .pth 后必须重启容器**才可 import |
| 只有 `sites/` 是命名卷，`apps/`、`env/` 在镜像层 | app 必须**烤进镜像**（改 `deploy/Dockerfile`；`.dockerignore` 目前只放行 Dockerfile，需同时放行 app 目录），不能在运行容器里装完就算 |
| 依赖 API 均可用 | `frappe.sessions.get_csrf_token()`、`frappe.db.savepoint/release_savepoint/rollback(save_point=)`、`frappe.database.savepoint(catch=...)`、`frappe.only_for()` |

### 6.2 最小 app 目录（仓库新增 `apps/m5_import_app/`，纯 Python，无 doctype / 无前端构建 / 无外部依赖）

```
apps/m5_import_app/
├── pyproject.toml                 # name=m5_import_app；依赖只有 frappe（环境已装）
├── README.md                      # 安装/验收/回滚
└── m5_import_app/
    ├── __init__.py
    ├── hooks.py                   # app_name/app_title/app_license/required_apps=["frappe"]
    ├── modules.txt                # "M5 Import"
    ├── api.py                     # @frappe.whitelist 的 preview_import / apply_import
    ├── importer.py                # 纯逻辑：六列解析、归一、去重判定、行计划（无 frappe.init）
    ├── writer.py                  # 事务写入：企业→联系人→Lead，逐行 savepoint
    └── www/
        ├── m5-import.html         # 页面（内联 JS，只做渲染与两次 POST）
        └── m5-import.py           # no_cache=1；get_context 校验登录/角色并注入 csrf token
```

- 页面走 module 的 `www/`，所以**不需要 `bench build`**（无 JS/CSS 资产）。
- `importer.py` 由 `tools/crm/m5_import.py` 迁移逻辑、去掉 `frappe.init/destroy`；CLI 保留为参考实现与回归基准，不删除、不继续扩写。

### 6.3 页面入口与调用契约

`GET /m5-import`（未登录跳登录页，角色不符 403）→ `m5-import.html` 内联 JS：

1. 选择/粘贴 CSV → `POST /api/method/m5_import_app.api.preview_import`（`csv_text`）→ 渲染逐行计划：行/序号/企业（新建|复用）/联系人（新建|复用(手机号|邮箱|姓名+企业)）/需求（新建|已导入|文件内重复）/错误原因，附汇总。
2. 用户确认 → `POST ...apply_import`（`csv_text`、`confirm=true`）→ 渲染逐行结果（docname 或错误），失败行可下载。
3. CSRF：`get_context()` 里 `frappe.sessions.get_csrf_token()` 注入模板，JS 带 `X-Frappe-CSRF-Token`。
4. 客户端**不含业务规则**，只做展示与请求；限制 ≤500 行 / ≤1MB。

### 6.4 服务端事务、幂等与并发

- `preview_import`：**只读**（不写库、不建 File），返回与 apply 相同的计划结构。
- `apply_import`：一个请求 = **一个事务**。每行 `savepoint("m5_row")` → 写企业→联系人→CSV 备注→Lead（写 `custom_import_key`）→ `release_savepoint`；行内异常 `rollback(save_point="m5_row")` 并继续下一行；全部行处理完才 `commit()`。异常中断则整批回滚，用户重跑安全（与原生 Data Import 的逐行 commit 不同，避免半成品与"重启后不知道导到哪"）。
- 幂等键：`sha256(企业归一|姓名|手机号或邮箱|需求归一)` **全长 64 位十六进制**，落在 `CRM Lead.custom_import_key`（`unique=1`）。先查后写；并发双击由唯一索引兜底 → 捕获 `DuplicateEntryError` 记为"已导入"（**不用备注文本解析，也不用历史 16 位截短 SHA1**）。
- 企业：docname（`organization_name`）天然键；联系人：手机号归一 → 邮箱小写 → 姓名+企业，按候选值精确查询（不做全表缓存）；联系方式原文进 `Contact.custom_contact_raw`，解析失败的行直接报错。
- `FCRM Note` 仍写一条人类可读来源备注（时间线可看），但**不再是幂等依据**；且因 M6 发现的 note 越权，**不得在其中放真实联系方式原文**（见 6.6 的字段分流）。

### 6.5 权限边界

- 两个方法 `@frappe.whitelist(methods=["POST"])`，方法内 `frappe.only_for(("System Manager", "Sales Manager"))`（专用角色由 M6 定，暂不新增角色）。
- 写入始终用调用者身份：`ignore_permissions=False`，逐 DocType 预检 `frappe.has_permission(doctype, "create")`；不以 Administrator 提权、不 `frappe.set_user`、不 `ignore_permissions`。
- 响应只含本次请求自己的行结果，不回传其他用户数据；CSV 不落盘为附件（避免私域文件扩散，需要留档时由用户另行决定）。

### 6.6 schema（与 UI 同一批，一次性设计；**未实施**）

| DocType | fieldname | 类型 | 用途 |
|---|---|---|---|
| CRM Lead | `custom_requirement` | Text（`search_index=1`、`in_list_view=1`） | 需求原文，可检索/可筛选 |
| CRM Lead | `custom_import_key` | Data（`unique=1`、`search_index=1`、read_only） | 幂等标识（唯一索引即并发兜底） |
| CRM Lead | `custom_import_source` | Data（`search_index=1`） | 来源：`文件名#行号/序号` |
| CRM Organization | `custom_product_offering` | Small Text | 产品/服务原文（与整理版 `company_description` 分开） |
| Contact | `custom_contact_raw` | Small Text | 联系方式原文（含微信等不可解析片段） |

- 渠道沿用现有 `source`（Link → CRM Lead Source，写 `M5导入样例`）；`FCRM Note` 只作人类可读时间线，**不放真实联系方式原文**（M6 已证实跨用户读取/改写）。
- 迁移：`bench export-fixtures` 固化 → `bench migrate`（ADD COLUMN + 索引）→ 一次性回填脚本把已有**合成**备注里的需求/原文搬到新字段 → 适配器与页面同时写字段。
- 回滚（更正）：**不做 `uninstall-app`、不删 Custom Field**。改为①先做 `bench backup --with-files`；②停用入口（下线 `/m5-import` 路由/撤回白名单方法）并保留字段与数据；③确需回退结构时用备份在同版本站点恢复，而不是删列。删字段会丢数据且不可审计，已从建议中移除。
- 与 M6：全部为非权限字段，不改角色/共享/owner；但仍须排在 M6 验证快照之后，由 tower 统一排期（本任务不实施）。

### 6.7 部署动作（需 tower 派单 + M6 暂停写入窗口）

1. 仓库：新增 `apps/m5_import_app/**`；`deploy/Dockerfile` 增 `COPY apps/m5_import_app ./apps/m5_import_app` + `pip install -e ./apps/m5_import_app`（在 `bench build` 之前）；`.dockerignore` 放行该目录；`deploy/README.md` 记录镜像与版本。**这三处超出 M5 现有 scope，需派单扩 scope。**
2. `python3 deploy/manage.py build`（生成新不可变镜像 ID，`deploy/.runtime/image.env` 覆盖前先记下旧 ID 用于回滚）+ `manage.py check`。
3. 通知 M6 暂停写入 → `python3 deploy/manage.py up`（recreate `backend`、`websocket`、`queue-short`、`queue-long`、`scheduler`；`frontend` 无资产变化可不重建）。
4. `bench --site crm.localhost install-app m5_import_app`（无 doctype → 不触发 migrate）+ `bench --site crm.localhost clear-cache`；随后按 6.6 应用 fixtures（可选批次）。
5. 验收（`M5UI2` 前缀合成数据）：`GET /m5-import` 登录门 → preview 计划正确 → apply 得到 2 企业/3 联系人/4 需求/3 错误行 → 二次 apply 0 新增 → 并发双击只落一份 → 无该角色账号 403 → 无邮件/队列副作用 → 与 `tools/crm/m5_import.py preview` 逐行一致。
6. 回滚（更正）：先 `bench backup --with-files`；停用入口（撤下 `/m5-import` 路由与白名单方法）、保留字段与数据；确需回退结构/版本时用备份在同版本站点恢复 + 旧镜像 `up`。**不**用 `uninstall-app` 或删字段当回退手段。

### 6.8 状态

- 本节是交给 M7 的实现输入；**M5 不实施**，未写 app、未改共享实例、未重启服务。M7 目前仍在部署测试，**未验收**。
- M5 的可审查增量是第 2–5 节的实测结果、`tools/crm` 脚本（含合成数据防护）与合成样例；它们**不**等于界面闭环。

## 7. 未实现边界与转交

1. **六列网页导入与服务端安全写入**：已转交 M7（方案见第 6 节），M7 部署测试中、未验收；M5 不实现 UI。
2. **可视 UI / 移动端 / PWA 安装**：未验收，待 tower 协调（内置浏览器不可用）。
3. **团队权限与私域隔离**：M6 已证实现有缺陷（FCRM Note 私密 detail/PUT 跨用户 200、activities 泄漏未共享 note），修复前**不得导入真实资料**；修复结论由 M6/M7 跟进。
4. **需求/产品原文的可检索落位**：6.6 的字段方案未实施，随 M7 的 schema 批次走。
5. **备份/恢复、重启持久化、导出关系**：未重测，需同版本新站点恢复演练。
6. **历史合成记录（未删除）**：`M5NATIVE` 6 条、`M5UI` 2 条（含 1 条重复）、若干 `Data Import`/`Data Import Log`；属对比证据，清理须 tower 批准。
7. 参考脚本按小数据集设计：联系人去重会把 `Contact Phone`/`Contact Email` 全量读进内存（当前 3 条），量级上千应改查询方式；该脚本已被 M7 取代，不再演进。
8. 调度器现为**开启**（原值 0，回退 `disable-scheduler`），见 2.1；公开更新元数据检查按要求不停用。

## 8. 复评触发条件

- M7 的六列网页导入验收后 → 由 M7 记录真实结果；M5 不重复声明。
- M6/M7 修复 FCRM Note 与 activities 的越权后 → 重新评估"原文备注"能否用于真实资料；在此之前仅合成数据。
- 6.6 的字段批次落地（tower 排期、M6 快照之后）→ 重测需求筛选，并更新 M3 schema 交接。
- 站点调度器/导入配置变化，或升级到带新导入 UI 的 CRM 版本 → 重测原生导入。
- 备份/恢复演练与视觉验收完成后，才谈"完整 MVP"。

## 9. R1 独审修复记录（2026-10-31）

| 问题 | 修复 |
|---|---|
| P1：仅名字前缀不构成安全边界，真实样式载荷可被接受后写入越权 Note | `preview`/`apply` 均先过**仓库可信摘要闸门**：文件内容必须与提交样例归一化 SHA-256 完全一致（摘要写死在 `m5_guard.TRUSTED_SAMPLES`，不接受调用方自报哈希），任何联系方式/产品/需求/来源改动都会失配被拒；行级前缀检查降为第二层。`preview` 额外声明"仅解析演示、不是真实数据路径" |
| P1：工作流只校验 Lead 前缀，Contact 按姓名猜、Deal 未逐项验证 | Lead 按历史导入键 + 三项身份核对；Contact 按手机号 + 姓名 + 企业 + Dynamic Link 唯一匹配；Deal 复用前核对 lead/organization；Task 只按已验证商机的 reference 复用。任一不符即中止 |
| P2：交接声称"改为全长 SHA1"，代码仍是 16 位 | 保留 16 位历史算法（改长度会让旧合成数据重跑重插）；此前提交说明与交接中的"全长 SHA1"说法**作废**，以本文件与代码为准；生产幂等由 M7 用完整 SHA-256 |
| P2：`ensure_source()` 在行循环前插入但未提交，首行失败会连带回滚并级联 | 改为 `apply_row()` **每行**调用 `ensure_source()`（幂等）；某行失败只回滚该行，后续行重建 Source |

本地回归（不写共享实例）：`python tools/crm/selftest_guard.py` 覆盖
①可信摘要命中；②"合法前缀 + 真实样式联系方式/需求"被拒；③只改一个手机号数字的副本被拒；
④CRLF+BOM 同内容被接受（摘要按 LF 归一）；⑤`import_key` 仍为 16 位（AST 断言）；
⑥`apply_row` 内调用 `ensure_source`（AST 断言）。输出 `PASS`；四个脚本 `py_compile` 通过。

**仍未复验**：以上修复未在共享实例端到端执行（窗口先归 M6、后归 M7）。复验方案见第 10 节；
其中"首行失败隔离"用**仓库内已登记的失败样例**触发，不改样例内容、不放宽闸门。通过前 M5 不申请完成。

## 10. 复验方案（待授权窗口；当前不执行）

> 修正说明（回应 tower 21:15）：先前方案写的"把某行 Company 置空来制造失败"与可信摘要闸门自相矛盾——
> 改样例会失配被拒，放宽闸门又等于拆掉防护。现改为**在仓库里预先登记一个专门的失败样例**，
> 失败由数据本身确定性触发（写入期超长），闸门保持原样、没有生产旁路开关。
> 同样，"首跑 2 企业/3 联系人/4 需求"不能拿历史样例硬套：该样例在本站点已导入过，重跑按设计应 **0 新增**；
> 首跑验收改用**新身份的新样例**，两套对象互不复用、互不覆盖。

### 10.1 三个受控样例（均已登记 SHA-256，改动即被拒）

| 样例 | 用途 | 预期 |
|---|---|---|
| `samples/m5-synthetic-six-columns.csv`（历史，M5 前缀） | 幂等/兼容：旧 16 位键仍能命中 | preview 5 跳过 + 3 错误行；apply **0 新增** |
| `samples/m5-synthetic-acceptance.csv`（新，M5UI2 前缀） | 首跑验收：全新对象，不与历史记录复用 | 2 企业 / 3 联系人 / 4 需求 / 1 文件内重复 / 3 错误行；二次 apply 0 新增 |
| `samples/m5-synthetic-write-failure.csv`（新，M5TXN 前缀） | 事务隔离：第 1 行企业名 149 字符（Data 上限 140），写入期确定性失败 | 第 1 行失败且无残留对象；第 2 行仍成功；`CRM Lead Source` 仍存在 |

三者的关系：可信清单按文件逐一登记（`m5_guard.TRUSTED_SAMPLES`），身份前缀不同、对象名不同，
所以既不会误复用历史 M5 对象，也不需要改动任何既有载荷。

### 10.2 具体命令（窗口内按序执行，全部在容器内）

```sh
# 0) 只读准备：复制脚本与三个样例
docker cp tools/crm/m5_import.py        crm-mvp-v15-backend-1:/tmp/m5/
docker cp tools/crm/m5_guard.py         crm-mvp-v15-backend-1:/tmp/m5/
docker cp tools/crm/m5_workflow_demo.py crm-mvp-v15-backend-1:/tmp/m5/
docker cp samples/ crm-mvp-v15-backend-1:/tmp/m5/samples/

# 1) 历史样例：幂等与旧 key 兼容
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 ../env/bin/python   /tmp/m5/m5_import.py preview --csv /tmp/m5/samples/m5-synthetic-six-columns.csv
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 ../env/bin/python   /tmp/m5/m5_import.py apply --csv /tmp/m5/samples/m5-synthetic-six-columns.csv --confirm   # 期望 0 新增

# 2) 验收样例：首跑 + 重跑
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 ../env/bin/python   /tmp/m5/m5_import.py preview --csv /tmp/m5/samples/m5-synthetic-acceptance.csv
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 ../env/bin/python   /tmp/m5/m5_import.py apply --csv /tmp/m5/samples/m5-synthetic-acceptance.csv --confirm     # 2/3/4
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 ../env/bin/python   /tmp/m5/m5_import.py apply --csv /tmp/m5/samples/m5-synthetic-acceptance.csv --confirm     # 0 新增

# 3) 事务隔离样例：首行失败、次行成功、Source 存活
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 ../env/bin/python   /tmp/m5/m5_import.py apply --csv /tmp/m5/samples/m5-synthetic-write-failure.csv --confirm

# 4) 工作流（只操作既有 M5 受控对象，逐目标校验）
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 ../env/bin/python   /tmp/m5/m5_workflow_demo.py --confirm

# 5) 只读收据
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 ../env/bin/python -c "
import frappe, json
frappe.init(site='crm.localhost', sites_path='.'); frappe.connect()
print(json.dumps({
 'm5ui2_orgs': frappe.db.count('CRM Organization', {'organization_name': ['like', 'M5UI2样例%']}),
 'm5ui2_contacts': frappe.db.count('Contact', {'company_name': ['like', 'M5UI2样例%']}),
 'm5ui2_leads': frappe.db.count('CRM Lead', {'organization': ['like', 'M5UI2样例%']}),
 'm5txn_leads': frappe.db.count('CRM Lead', {'organization': ['like', 'M5TXN%']}),
 'source_exists': bool(frappe.db.exists('CRM Lead Source', 'M5导入样例')),
 'email_queue': frappe.db.count('Email Queue'), 'communications': frappe.db.count('Communication'),
 'webhooks': frappe.db.count('Webhook'), 'notifications': frappe.db.count('Notification'),
}, ensure_ascii=False, default=str))
frappe.destroy()"
```

### 10.3 断言与失败处理

- 步骤 1：输出 `企业=0 联系人=0 需求=0 需求跳过=5 错误行=3`；若出现新增，说明旧 16 位键未命中 → 停止并报告，不改算法。
- 步骤 2：首跑输出 2/3/4（1 文件内重复、3 错误行）；重跑 `0/0/0`。
- 步骤 3：结果 JSON 中第 1 行 `状态=失败`（异常含长度/字段信息），第 2 行 `状态=成功`；
  且 `M5TXN` 只有第 2 行的企业/联系人/需求，`source_exists=true`（证明 Source 未被首行回滚吞掉）。
- 步骤 4：两商机 `已存在`、阶段无新变更、任务 `已存在`、无新评论；若出现新评论/任务说明幂等退化。
- 任一断言不符，只收集输出并回报，不删除数据、不改闸门、不重跑覆盖。
- 保留物：`M5UI2`/`M5TXN` 前缀合成记录与相关 `Data Import`/备注，均不删除，作为复验证据。

### 10.4 本轮已完成的替代验证（不能替代实例复验）

- 本地 `selftest_guard.py`：三个可信样例摘要全部命中；真实样式载荷、单点改动被拒；CRLF+BOM 归一；
  16 位历史键断言；`apply_row` 自保 `Source` 断言（AST 仅作补充，**不作为**事务失败的真实证明）。
- 事务失败隔离的真实验证只能在窗口内由 10.2 步骤 3 完成。

## 11. 窗口内真实回归结果（2026-10-31，M6 释放窗口后执行）

运行环境：`crm-mvp-v15`，镜像 `36a89c9b0ad6`（M7 部署中，`resource_import 0.1.0` 已安装），
站点 `crm.localhost` 的 `allow_error_traceback` 已由 1 改为 0。脚本在容器内经 `env/bin/python` 运行，
不依赖 HTTP/浏览器；全程未改 schema、未重启服务、未改账号权限、未删除任何记录。

### 11.1 历史样例：幂等与旧 16 位键兼容（§10 步骤 1）
- preview：`企业=0 联系人=0 需求=0 需求跳过=5 错误行=3`（与预期一致，退出码 2）。
- apply 后再查库：`M5样例*` 仍是 **2 企业 / 3 联系人 / 4 需求** —— **0 新增**，旧 16 位导入键命中正常。

### 11.2 新身份验收样例 M5UI2：首跑与重跑（§10 步骤 2）
- preview：`企业=2 联系人=3 需求=4 需求跳过=1 错误行=3`。
- 首跑 apply：创建 2 企业 / 3 联系人 / 4 需求（`CRM-LEAD-2026-00028`~`00031`），1 行文件内重复跳过，3 行按行报错。
- 重跑 apply：`企业=0 联系人=0 需求=0 需求跳过=5 错误行=3`；库中仍为 **2/3/4** —— 无重复。

### 11.3 固定 M5TXN 样例：写入期失败隔离（§10 步骤 3）
- 第 1 行（企业名 149 字符）真实写入期失败：`CharacterLengthExceededError: CRM Organization … 'Organization Name' … max characters allowed is 140`。
- 第 2 行仍成功：企业 `M5TXN样例企业乙`、联系人 `样例故障乙-M5TXN样例企业乙`、需求 `CRM-LEAD-2026-00032`（`source=M5导入样例`）。
- 复查：库中**没有**被截断或残留的故障行企业；`M5TXN` 仅 1 企业 / 1 需求；`CRM Lead Source: M5导入样例` 存在。
- **诚实的限定**：`M5导入样例` 这个 Source 在本次运行前就存在，所以"Source 首次插入未提交、被首行回滚连带删除"的原始触发条件在本站点无法复现（要复现需删除该 Source 或换全新站点，均未被授权）。本轮能确证的是：**首行写入失败不再影响后续行，且 Source 状态良好**；该修复的结构性依据是 `apply_row()` 每行调用 `ensure_source()`。

### 11.4 业务工作流：写目标校验与无重复（§10 步骤 4）
- `m5_workflow_demo.py --confirm` 退出码 0，全部为"已存在"：商机 `CRM-DEAL-2026-00001/00002`、2 个跟进任务、4 条评论；
  阶段无新变更（`stage_changes` 均为空）、商机字段"已有值，未覆盖"、联系人已是生产经理。
- 全部 checks 为 true（两商机不同、各自有企业/需求/联系人、各有未完成跟进、阶段记录与时间线、转换状态）。
- 说明：Lead/Contact/Deal/Task 的受控身份与关系校验均通过（否则会直接中止），没有误改任何非目标对象。

### 11.5 只读收据（§10 步骤 5）
```
M5: 2 企业 / 3 联系人 / 4 需求      M5UI2: 2 / 3 / 4      M5TXN: 1 企业 / 1 需求
M5 商机 2，M5 任务 2                CRM Lead Source(M5导入样例) 存在
Email Queue 0   Communication 0   Webhook 0   Notification 0
```
未删除任何记录；`M5UI2`（2/3/4）与 `M5TXN`（1/1）作为本次复验证据保留，前缀明确、可识别。

### 11.6 结论与边界
- §10 的四组断言全部满足；未出现需要停手定位的预期不符。
- 仍未覆盖：真实的跨用户权限（M6）、六列网页导入（M7）、可视验收、备份/恢复。
- 本轮结论仅针对 **M5 合成工具链**，不代表 MVP 完成。
