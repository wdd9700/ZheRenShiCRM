# Team Activity Access 0.1.0（M8 / D005）

**状态：实现与离线核验阶段；尚未安装共享实例，尚未通过双Sales User真实HTTP、视觉和独立审查。不是团队MVP权限验收。** 固定目标为 Frappe 15.125.0 + CRM 1.90.0（CRM commit `36bd8859f2a6345a620477bc708d0546e8c3f08a`）。只新增独立 `apps/team_access`，不改Frappe/CRM核心、全局角色、Administrator凭据或既有M5/M6/M7合成业务数据。部署归tower/M9，未获窗口不得执行本页写入命令。

## 1. 已确认语义

本页汇总tower在实施前确认的D005暂选，决策日志由其拥有者维护，不在本分支重复修改。

| 对象/操作 | 首版规则 |
|---|---|
| Private Note / Task | 默认；仅owner、单一明确读写协作者，以及Task的有效assigned_to可读写。Private不等于只有owner。 |
| Shared Note / Task | owner明确发布**当前正文**给关联父记录所有现有和未来读者；不自动授予写入、历史版本或附件权限。 |
| 写正文 | owner/明确协作者/Task受派人；有父时三者仍须父可读。父只读者不能借Shared写子文档。 |
| 变更授权 | 仅owner或受信Administrator可改visibility/collaborator/assigned_to/关联；普通协作者不能再授权或移动父记录。普通API不支持转移owner。 |
| 独立活动 | 两个reference字段均空时可建Private；可给明确协作者。禁止Shared。单边空、未知父类型、缺失父拒绝。 |
| 有父活动 | 仅支持CRM Lead/CRM Deal；每次读取和写入重新检查父read。撤回父权限立即阻断后续请求。 |
| 历史/通知 | Note/Task历史Version和其下Comment/Communication仅owner/协作者/受派人可读。Shared读者不读过去Private原文或旧通知副本。授权新协作者会授予既往历史，UI需确认。 |
| 正式Comment | Lead/Deal上的Comment是向父读者发布的共享沟通，不是私人备忘。编辑器旁明确提示；私人长文使用Private Note。 |
| 附件 | 仅本地private storage，直链也检查父和活动授权。Private附件仅owner/协作者；Shared首版只支持无附件正文，不能直接把含附件/内嵌私有文件URL的活动切Shared。应保留原Private，另建不含附件的共享摘要，不自动复制私密历史。独立管理页不提供上传。 |
| Call Log | 保守整行规则：所有直接父和动态关联Note/Task等必须可读，否则整个Call不返回，连raw `note/links`候选ID也不返回。可能少显示含私人备注的通话，不假装完整。 |
| Administrator | 沿用受信框架管理员的数据管理能力，不改账号/全局角色。普通Sales Manager/System Manager并不因此获得Private正文；本app不给其隐式私域旁路。文件落盘不允许公开活动私文的存储不变量也约束普通File保存路径。 |

单一协作者字段是可逆的首版限制，不是完整团队成员ACL。正式企业/联系人仍沿用既有模型，未在本app改为私域。没有新增逐记录User Permission；既有DocShare不作为Note/Task授权来源。原生私密活动DocShare创建被拒绝；父Lead的显式共享仍沿用原生功能。旧DocShare行保留，但不能突破本app规则。

## 2. 为什么不是一个has_permission hook

只读固定运行源码已确认：

- `frappe/permissions.py::has_permission`在controller False后回退DocShare；`model/db_query.py::build_match_conditions`在query条件后再OR DocShare。仅返回False或只有query hook不足。
- `crm/api/activities.py`用get_all/QB读子Note/Task/Call，且Note派生活动包括分组`other_notes`与Version pin事件；`get_docinfo`还另写顶层response。只过滤notes数组会漏正文或候选。
- `crm/api/doc.py::set_activity_counts`用get_all；`fcrm_note.py::notify_mentions`复制正文到CRM Notification；`integrations/api.py`对已有Note/Task用ignore_permissions更新。
- `desk/reportview.py::_export_query`用selected_items**覆盖**filters，随后DatabaseQuery导出，没有逐文档补救。
- `File.before_insert`先落盘，再进入常规before_validate；因此文件校验不能只加事件。CRM `www/crm.html`是独立完整SPA模板，不包含普通web_include_js注入点。

实现使用官方扩展点：统一`permissions.permitted`谓词；hard-deny权限hook阻断DocShare详情回退；query hook；**限定已审查入口**的auth_hook额外AND name-in过滤（不是SQL文本补丁或全局monkeypatch）；whitelist override聚合/关联/计数/侧响应；doc_events治理写入；File官方doctype子类先校验再super；after_request只对CRM 200 HTML插同源脚本。query SQL只拼固定DocType标识和数据库escape的授权ID，HTTP附加过滤使用框架结构化filters。

## 3. 已实现入口与兼容性边界

| 入口 | 机制 / 必测负例 |
|---|---|
| REST v1 resource、v2 document/count | detail写入由hook+事件；collection额外AND授权ID；私密和不存在的直接ID都403。 |
| frappe.client get/list/value/count/set_value/save/insert/delete | query/hard-deny/事件；列表额外AND。批量字段变更不能伪造owner或先换父再借新父权限。 |
| reportview get/get_list/get_count/export_query | 同谓词AND过滤；selected_items转为额外filter，不允许覆盖；受保护类型禁止后台旧授权导出。 |
| Data Import download_template、Data Export exporter | 精确export_filters/filters额外AND；非管理员多DocType导出拒绝，需逐类型审查后再放开。 |
| search_link/search_widget | 额外AND；受保护类型不接受任意自定义query/ignore_user_permissions绕过。 |
| CRM get_data | 保留分页/视图；Note/Task限定合法ID；父卡片Note/Task/Comment/Communication计数按允许子记录重算。 |
| activities | 检查父；过滤notes/tasks/calls/attachments与分组/派生事件；去掉另一个顶层docinfo。 |
| 原生getdoc/get_docinfo | 对受保护文档逐项过滤versions/comments/communications/attachments/assignments；Shared只读者不见历史用户信息、访问记录和未审查可选timeline历史。不会清空其他DocType的历史语义。 |
| 关联候选 | CRM get_linked_docs、Desk linked_with、dashboard get_open_count重新按可读对象生成。 |
| Call get_call_log / add_note/task_to_call_log | 不复用跨请求cached_doc返回体；检查当前Call和已有子write；新建走当前会话正常save，不ignore_permissions。 |
| mentions / notifications | 未授权mention使保存拒绝，不产生新正文通知；既有通知不删，读取按当前目标权限过滤。 |
| File | File子类before_insert/validate；直接upload入口在处理字节前检查；禁止活动public/remote/url复用，禁止已私有活动文件detach/reparent/公开转换。 |

`frappe.desk.notifications.get_open_count`保留原生dashboard关联规则的internal names/count与external count/open_count；**不执行DocType模块的任意get_timeline_data回调**，因此依赖该可选回调的Desk额外时间轴片段不受支持，原生CRM主时间线使用单独activities override。需真实UI确认固定版本实际受影响部位，不把缺片段当成功。

受保护类型全表扫描最大2000行（每类型），取2001确认超限；不截断成“授权集合”。超限整请求拒绝，返回`team_access_limit:2000`，管理页明确显示容量拒绝，不返回伪空列表。没有跨请求自建权限缓存；大数据前必须重评可索引ACL方案，不能提高常数冒充可扩展设计。未审查且显式指定受保护doctype的RPC拒绝；未来新增whitelisted方法、app或版本必须复核，不能声称本app能约束任意第三方get_all代码。

## 4. 可操作UI与缓存风险

`/team-activities`为登录网页：原生允许范围内的Note/Task列表、Private创建、当前正文编辑、owner显式Shared/撤回、单一协作者/Task受派人设置。父候选仅取当前会话CRM Lead/Deal get_list结果；协作者需完整已知账号，不提供额外用户资料枚举。共享和授权历史都有确认提示。原生Desk表单加入口，CRM SPA通过狭窄after_request HTML注入静态`access.js`；脚本在动态实际编辑器旁加正式Comment共享提示和管理页入口。

- 注入只改`/crm`及其路由200 `text/html`，不改重定向、API JSON/下载或CSP；Response.set_data更新Content-Length。同源script必须被实际CSP允许；无inline脚本依赖。
- API、管理页、CRM HTML no-store/private；这不清除已经下载的旧PWA Service Worker cache、浏览器内存、合法导出文件或此前漏洞泄露的副本。
- 安装前所有旧会话退出，停止旧Python服务；安装后clear-cache、所有服务同版本重建、浏览器清站点数据/注销旧Service Worker再登录。须验证**同会话授权撤回**和重启后再登录，不只换账号拿一个新会话。
- 浏览器视觉、MutationObserver编辑器覆盖、CSP、PWA离线与重启缓存仍未测。JavaScript缺失不能被HTML200代替验收。没有接触真实私域资料。

## 5. 版本化安装/迁移与M9集成

### 0.1.0候选安装顺序（仅tower窗口）

1. 保存当前源码/镜像锁和installed apps清单；maintenance mode，停止业务写入和队列，备份数据库及public/private files。先完成M7/M6/M5交接，不能两人同时schema改库。
2. **预检先于install-app/migrate写入**：在包含候选app代码但尚未启用app的镜像中显式执行`bench --site crm.localhost execute team_access.install.preflight`。它检查精确版本和所有Note/Task及其Comment/Communication间接附件，发现公共/远程附件只报受影响数量并拒绝；通过受控Administrator File列表定位。绝不自动移动、删除、公开、改正文；此情况需另立经过备份/校验的迁移，不能略过预检。
3. M9镜像从当前M7集成基底补入`apps/team_access`，`env/bin/pip install --no-deps -e apps/team_access`，`bench build --app team_access`并将assets复制到镜像资产目录。无新运行依赖，无npm项目或Vue上游改动；保持resource_import。configurator的apps.txt须包含team_access，不覆盖site_config。
4. 执行`bench --site crm.localhost install-app team_access`与`bench --site crm.localhost migrate`；install和after_migrate创建/校验两个Custom Field，旧空可见性按Private处理，不把旧记录设Shared、不改原文。已存在同名不兼容fieldtype/options/default时拒绝。记录app版本0.1.0与提交SHA；迁移可重入。
5. `bench --site crm.localhost clear-cache`，重建所有Python/worker/调度/socket服务及前端到同候选镜像，不能只更新backend。核验静态JS资产可达、所有服务installed app import成功、maintenance窗口内先做只读预检。
6. 双Sales User脚本、真实原生UI/独立页、匿名/无角色、CSRF、导出、附件、缓存与重启矩阵全过，再提交独审并解除维护。任何一项失败仍是MVP阻断，禁止将编译/管理员ORM等同验收。

### 安全回退

不能直接切回缺team_access的旧镜像，不能uninstall-app、删字段或停hook（before_uninstall明确拒绝）。安全回退镜像必须保留本版或经审查兼容的安全app及全部hook；维护模式下可关闭管理页/新写入，但不可关闭读权限边界。修复失败保持维护/停止服务并保留数据，不以开放旧API“恢复可用”。如确需完全撤掉app，先将私域正文、历史、通知与文件在隔离恢复站点作经过授权的安全迁移/验证，另行评审，不自动执行。全量恢复只能恢复到同一安全扩展版本并验证；备份成功不代表恢复已通过。

## 6. 双真实Sales User重复核验

驱动`apps/team_access/verify_http.py`使用标准库HTTP、两个独立CookieJar、真实密码会话和CSRF；不调用docker/ORM/Administrator，不创建用户、不改角色/User Permission，只创建带唯一M8前缀的**新合成fixture**。只修改manifest中经owner+前缀核验的M8记录，不改M5/M6/M7。凭据通过getpass或进程环境`TEAM_ACCESS_PASSWORD_A/B`，不打印、不落manifest、不提交；不要把密码放命令行、shell history或日志。manifest只有合成ID/marker，放app忽略的`.local`。

在tower给出的窗口内，先用两个已经存在、仅Sales User角色的账号。为了测试真实旧DocShare OR，**必须在首次安装前**prepare legacy fixture（只对新M8活动创建旧原生DocShare；这是攻击回归fixture，不是生产修复）。安装后verify；每一完整重跑使用新的manifest/prepare，脚本拒绝覆盖旧manifest，不删除fixture。

```sh
python apps/team_access/verify_http.py prepare --user-a <SalesUserA> --user-b <SalesUserB> --fixture apps/team_access/.local/m8-run1.json --legacy-shares
# tower/M9：预检、备份、安装候选、安全重建
python apps/team_access/verify_http.py verify --user-a <SalesUserA> --user-b <SalesUserB> --fixture apps/team_access/.local/m8-run1.json
```

脚本不输出响应体或异常堆栈，只输出固定PASS/FAIL标签。失败保留合成记录供定位，不自动清理。首次安装后新prepare不加legacy-shares可重复大部分矩阵，但缺真实旧DocShare行会在最后明确失败，不能声称完整旁路验收。已有活动fixture第一次verify后会附着私有测试文件，不能把同一fixture重复跑的状态差异当权限故障；新建一组再跑。

自动矩阵：双向Private detail/REST write/list/native getdoc/count/search、CSV普通/selected、父activities/关联候选、Shared当前正文只读/过去Version拒绝、协作者正文写入/再授权拒绝/撤回、Task受派人写入/再分派拒绝/撤回、父权限撤回恢复、DocShare新建拒绝、正式Comment/不可见父Comment、未授权mention/notification、private File直链/公开转换/detach/公开插入和带附件发布拒绝。

**仍须人工/补充真实HTTP**：v2详细矩阵、原生CRM各动态编辑器提示及管理页视觉、只读Shared原生写按钮反馈、Call Log动态链接/已有子更新、get_docinfo顶层侧响应全部字段、Version直接detail与CSV、Data Import/Data Export全部导出变体、File旧URL复用/先无父后挂载/remote/multipart上传/间接Comment附件、匿名/无角色/CSRF、用户权限缓存撤回与重启、M5/M7兼容和备份恢复。脚本最终打印MANUAL REQUIRED，不把脚本通过称全边界验收。

## 7. 验证台账（交付时持续更新）

| 项目 | 当前证据 |
|---|---|
| 固定上游源码审查 | 已完成只读docker exec源码核对；未运行共享HTTP基线。M6真实Note越权事实由M6交接。 |
| Python/JS语法与diff检查 | 已过：13个Python文件AST、pyproject TOML解析、两个静态JS的node --check、verify_http.py --help、git diff --check；无共享HTTP。另用内存Frappe替身做了谓词/hard-deny/父撤回/协作者/历史/通知/File/Call/filters/HTML smoke，已过但不是真实框架权限验收。Windows无flit_core，未安装依赖；标准bench build/安装需M9候选镜像窗口，不能把AST当构建成功。 |
| 两Sales User真实会话 | 尚未获窗口，未执行。 |
| 安装/迁移/预检真实行为 | 未执行；M9负责镜像/维护/备份窗口。 |
| UI/CSP/PWA/重启 | 未执行。 |
| 独立审查 | 待源码候选提交后由tower安排。 |
| 规模/性能 | 2000行fail-closed边界仅设计实现；负载与多类型递归成本未测，不适用于真实规模上线。 |

当前无新增需要用户决定的技术卡点；D005是可逆暂选。真正阻断是部署窗口、真实全边界核验和独审，不用架构文档替代可观察权限证据。AGPL对应源码及修改说明须随网络服务履行适用义务，本页不构成法律意见。
