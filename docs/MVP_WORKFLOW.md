# MVP 业务闭环：资源导入 → 企业/联系人 → 需求 → 商机 → 沟通 → 下次跟进 → 时间线

**状态：首个不依赖 AI、不依赖自建 CRM 前后端的闭环已在真实实例上跑通。原生导入在受控开启站点调度后已能真实执行（含逐行错误），但"中文六列一次导入"这个用户界面体验仍未交付：缺自然键去重、缺多对象编排、需求列没有原生字段。CLI 适配器只是增量，不替代 UI 验收；可视界面验收待 tower 协调（内置浏览器控制不可用）。**

- 实例：`crm-mvp-v15`，站点 `crm.localhost`，入口 `http://127.0.0.1:8088/crm`（仅回环，合成数据）。
- 版本：Frappe Framework `15.125.0`，Frappe CRM `1.90.0`（`deploy/README.md` 已锁定的派生镜像）。
- 记录原则：只写**实际执行过**的结果；未执行的项目集中在第 7 节，不混进"已完成"。

## 1. 结论速览

| 能力 | 结果 | 证据 |
|---|---|---|
| 原生导入入口 | `/crm/data-import`、`/crm/data-import/doctype/:doctype`，v15 回落 framework 经典向导（上传→映射→预览→导入） | 前端源码 + SPA 路由 200 |
| 原生列映射 | 可用，但中文表头**不自动匹配**，必须人工按列映射（映射键是列序号，不是表头） | 预览 warnings 逐列 `Cannot match column 姓名/公司名称/…` |
| 原生"开始导入" | **原部署被调度器禁用挡住；受控开启后真实跑通** | 开启前 `ValidationError: Scheduler is inactive. Cannot import data.`；开启后 `start_import()`→`True`→状态 `Partial Success` |
| 原生逐行错误 | 可用（`Data Import Log` 每行一条，含异常正文） | 缺姓名行 `Error: Value missing for CRM Lead: First Name`；含微信/邮箱原文行 `… is not a valid Phone Number` |
| 原生重复控制 | **没有**自然键去重，同一文件导两次记录翻倍 | 同一 3 行文件走两次 UI 路径 → `CRM-LEAD-2026-00012` 与 `-00013` 同姓名同手机号 |
| 一次导入建企业+联系人+需求 | **不支持**（一次一个 DocType） | `Data Import.reference_doctype` 单值 |
| 六列里的"需求/产品"列落到 Lead | **无原生字段** | `CRM Lead` 元数据里没有需求文本字段 |
| 最小适配（CLI） | 已实现、真实库跑通、可重复执行不重复建记录 | `tools/crm/m5_import.py`：首次 2 企业/3 联系人/4 需求；二次 0 新增 |
| 需求→商机 | 原生人工转换（`convert_to_deal`），脚本**不会**自动建商机 | `CRM-DEAL-2026-00001`、`CRM-DEAL-2026-00002` |
| 沟通/跟进/阶段/时间线 | 已跑通 | 4 条评论、2 个 `CRM Task`、阶段日志、时间线接口 7 条活动 |
| 可视 UI 点击验收 | **未做** | 内置浏览器 `browser.create_tab` 返回 `BROWSER_UNAVAILABLE`；tower 已改用 Edge 协调 |

## 2. 原生导入实测（含调度器）

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

## 3. 最小适配：`tools/crm/m5_import.py`

容器内运行，Python 标准库 + 已安装的 frappe，无新依赖、无自定义字段、无数据库结构变更。

```
preview  只读，输出逐行计划与错误，退出码 0（无错误）/2（有错误行）/1（致命）
apply    真实写入，必须带 --confirm；退出码同上
```

| CSV 列 | 去向 | 去重/幂等方式 |
|---|---|---|
| 序号 | 写进来源备注，不当业务主键 | — |
| 姓名 | `Contact.first_name`（脚本命名如 `样例张一-M5样例企业甲 智能制造`） | 手机号 → 邮箱 → 姓名+企业，三级匹配 |
| 公司名称 | `CRM Organization`（docname 即企业名） | 同名即复用 |
| 联系方式 | 原文写入联系人 `FCRM Note`；解析出的手机号/邮箱写入 `phone_nos`/`email_ids` | 手机号按数字归一后匹配 |
| 公司产品、服务 | `CRM Organization.company_description` | 复用时只读不覆盖 |
| 需要的产品、服务 | **每条需求一条 `CRM Lead`**（`status=New`，`source=M5导入样例`）+ `FCRM Note` 保存需求原文 | 导入键 = SHA1(企业｜姓名｜手机号或邮箱｜需求原文) 前 16 位，写入备注 HTML 注释 `<!-- m5-import-key:… -->`，重跑按此跳过 |

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

## 4. 业务闭环演示：`tools/crm/m5_workflow_demo.py`

`--confirm` 才写库，缺省只读检查；重复执行不会重复建商机/评论/任务/阶段变更。

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

## 5. 用户可复现的操作路径

### 5.1 命令行（已验证）

主 checkout（合并后）在第一 Ubuntu 中执行：

```sh
cd /mnt/p/CRM
docker exec crm-mvp-v15-backend-1 mkdir -p /tmp/m5
docker cp tools/crm/m5_import.py crm-mvp-v15-backend-1:/tmp/m5/
docker cp tools/crm/m5_workflow_demo.py crm-mvp-v15-backend-1:/tmp/m5/
docker cp samples/m5-synthetic-six-columns.csv crm-mvp-v15-backend-1:/tmp/m5/
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 \
  ../env/bin/python /tmp/m5/m5_import.py preview --csv /tmp/m5/m5-synthetic-six-columns.csv
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 \
  ../env/bin/python /tmp/m5/m5_import.py apply --csv /tmp/m5/m5-synthetic-six-columns.csv --confirm
docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 \
  ../env/bin/python /tmp/m5/m5_workflow_demo.py --confirm
```

`/tmp/m5` 只是容器内临时目录，不进入镜像；脚本不读 `.env`、不打印密码。

### 5.2 CRM 界面（原生路径）

浏览器打开 `http://127.0.0.1:8088/crm`（Administrator）：

1. **Leads** 列表看 4 条 `M5样例*` 需求线索；详情 Activity 有导入备注（需求原文、企业提供、联系方式原文、来源行）与评论；状态可改。
2. **Deals** 列表看 2 条商机；`CRM-DEAL-2026-00001` 详情可改 `Status`/`Next Step`/金额/预计成交日，Activity 显示创建、阶段变更、评论，Tasks 显示 2026-11-03 跟进。
3. **Organizations / Contacts** 看企业主营与联系人的手机/邮箱/关联企业。
4. **需求转商机**：在需求线索页用原生"转换为商机"（人工动作）。
5. **导入**：`/crm/data-import` 上传 CSV → 人工映射列（中文表头需手选）→ 预览 → 开始导入。现在按钮可用（调度器已开启），逐行结果在导入结果页 / `Data Import Log`。

HTTP 级核对已通过：`/crm`、`/crm/leads`、`/crm/deals`、`/crm/data-import`、`/crm/organizations`、`/crm/contacts` 返回 200 SPA 外壳与 JS 资产；`frappe.client.get_list`（Lead/Deal/Task）、`frappe.client.get`（商机详情）、`crm.api.activities.get_activities`、`get_preview_from_template`、`form_start_import` 均返回真实数据/结果。

**未做**：浏览器内的可视点击验收。内置浏览器 `browser.create_tab` 反复返回 `BROWSER_UNAVAILABLE`，因此不声称"界面已验收"，只声称"前端调用的接口与原生导入链路已返回正确结果"。

## 6. 原生 UI 导入的缺口与适配方案（提案，未实施）

缺口（用户用界面导入六列 CSV 时实际会卡住的地方）：

1. 中文表头不自动映射，每次导入都要手工对六列；需求/产品两列根本无字段可选。
2. 一条 CSV 只能建一种对象，企业/联系人/需求要拆三次导入，且关系不会自动建立。
3. 联系方式原文会被 Phone 校验拒绝（实测 `… is not a valid Phone Number`）。
4. 重复导入直接翻倍，没有手机号/邮箱/企业名的自然键去重。

三个候选（按成本从低到高），**都未实施，等 tower 决定 scope**：

- **A. 预解析 + 原生 UI 执行（低成本，推荐先做）**：CLI 负责预览、去重、拆分与归一，产出三份"原生可直接导入"的 CSV：`CRM Organization`（`organization_name` 恰是 autoname 字段，可直接以 Update 模式去重）、`Contact`（手机/邮箱已归一，企业关系用 `company_name`）、`CRM Lead`（含 `name` 列用于 Update 模式）。用户在原生导入页分三次上传，界面体验、逐行错误、失败行下载都复用现成功能。代价：需求原文仍需落到备注（无字段），且要说明"先 CLI 预解析、再 UI 导入"的两段式。
- **B. 加一个自定义字段（小结构变更）**：给 `CRM Lead` 加"需求描述"自定义字段后，需求列就能在原生 UI 单文件导入并出现在列表/筛选里。需要站点 schema 决策（改共享站点结构），本轮未做。
- **C. 自建小型原生 Page（高成本）**：在 crm 前端加一个 Vue 自定义路由，把"上传六列 → 预览 → 确认"做成一页，内部调用 A 的解析服务 + 原生 Data Import。需要前端构建链与对 crm 应用的源码改动，超出本任务 scope，且与"不另建一套 CRM"的边界要重新确认。

建议顺序：先 A（不改结构、当天可用），把 B 作为 schema 决策项提交，C 只在用户明确要求"界面一键导入"时再评估。

## 7. 未实现边界与待决事项

1. **可视 UI / 移动端 / PWA 安装**未验收；tower 将用 Edge 协调。
2. **六列 CSV 的界面一键导入**未实现（见第 6 节 A/B/C 提案）。
3. **团队权限与双账号私域隔离**未验证：全程只有 `Administrator` 一个账号。
4. **需求文本没有原生字段**，现在只在 `FCRM Note` 里；能否按需求筛选/看板取决于是否采纳 B。
5. **备份/恢复、重启持久化、导出关系**未在本轮重测（`deploy/README.md` 有备份口径，需同版本新站点恢复演练）。
6. **原生导入试验留下的合成记录（未删除，唯一前缀）**：`M5NATIVE` 6 条、`M5UI` 2 条（含 1 条重复）、若干 `Data Import` 与 `Data Import Log`。它们是对比"原生去重缺失/逐行错误"的证据；如需清理须由 tower 另行批准。
7. 适配器按小数据集设计：联系人去重会把 `Contact Phone`/`Contact Email` 全量读进内存（当前 3 条）；量级上千后应改成按候选值查询或建索引。
8. 调度器现为**开启**状态（原值 0），回退命令见 2.1；两条 Weekly Long 的应用更新元数据任务未执行、也未停用。

## 8. 复评触发条件

- 采纳第 6 节任一方案 → 重测界面导入体验，并把结果补进本文件与决策链。
- 站点调度器/导入配置变化，或升级到带新导入 UI 的 CRM 版本 → 重测原生导入。
- 需要按需求文本筛选/看板 → 评估加自定义字段（并同步 M3 schema 交接文档）。
- 出现第二位真实账号 → 立即补双账号权限与私域隔离验收，再谈"团队 MVP"。
- 真实客户资料进入系统前：先做备份/恢复演练、访问边界与授权确认。
