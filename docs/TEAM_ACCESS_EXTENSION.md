# Team Activity Access 0.1.0（M8 / D005）

**状态：实现与离线核验阶段；尚未安装共享实例，尚未通过双Sales User真实HTTP、视觉和独立审查。不是团队MVP权限验收。** 固定目标为 Frappe 15.125.0 + CRM 1.90.0（CRM commit `36bd8859f2a6345a620477bc708d0546e8c3f08a`）。只新增独立 `apps/team_access`，不改Frappe/CRM核心、全局角色、Administrator凭据或既有M5/M6/M7合成业务数据。部署归tower/M9，未获窗口不得执行本页写入命令。

**候选仍不可部署，待exact-tip独审及真实验收。** 固定Lead/Deal源码已确认没有`no_feed_on_delete`或独立删除hook，原生`delete_doc.insert_feed`确会产生被本扩展拒绝的半空Comment引用。现已使用两个官方controller窄子类**仅关闭普通父删除feed**，所有业务方法完全继承；固定实际`insert_feed`离线调用已通过兼容回归。不放宽半空引用，不信任客户端Deleted类型，不改删除快照持久化。真实CRUD、关联/权限检查和快照保留仍未测，不能把离线函数通过当“删除通过”。

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

实现使用官方扩展点：统一`permissions.permitted`谓词；hard-deny权限hook阻断DocShare详情回退；query hook；**限定已审查入口**的auth_hook额外AND name-in过滤（不是SQL文本补丁或全局monkeypatch）；whitelist override聚合/关联/计数/侧响应；doc_events治理写入；File官方doctype子类先校验再super；官方controller子类抑制私域通知；after_request按对象范围清理JSON历史缓存/链接标题，HTML注入仅限CRM 200页面。query SQL只拼固定DocType标识和数据库escape的授权ID，HTTP附加过滤使用框架结构化filters。

## 3. 已实现入口与兼容性边界

| 入口 | 机制 / 必测负例 |
|---|---|
| REST v1 resource、v2 document/count | detail写入由hook+事件；collection额外AND授权ID；私密和不存在的直接ID都403。 |
| frappe.client get/list/value/count/set_value/save/insert/delete | query/hard-deny/事件；列表额外AND。批量字段变更不能伪造owner或先换父再借新父权限。 |
| reportview get/get_list/get_count/export_query | 同谓词AND过滤；selected_items转为额外filter，不允许覆盖；受保护类型禁止后台旧授权导出。 |
| Data Import download_template、Data Export exporter | 精确export_filters/filters额外AND；非管理员多DocType导出拒绝，需逐类型审查后再放开。 |
| search_link/search_widget | 额外AND；受保护类型不接受任意自定义query/ignore_user_permissions绕过。 |
| CRM get_data | 保留分页/视图；Note/Task限定合法ID；父卡片Note/Task/Comment/Communication计数按允许子记录重算。 |
| activities | 检查父；过滤notes/tasks/calls/attachments与分组/派生事件；去掉另一个顶层docinfo。Communication在投影丢name之前，复用固定版本原生`_get_communications`保留权威ID逐条判权后重建相同活动结构和附件过滤，不使用文本指纹；含私域主引用或timeline链接的整条通信按私域历史权限限制。沿用每父最新21条窗口，过滤后可能少于21条，不补抓更老记录；转换Lead仍须当前可读，保留Lead先于Deal、creation降序稳定排序和重复关联。 |
| 原生getdoc/get_docinfo/get_communications | 对受保护对象**和CRM Lead/Deal父记录**逐项过滤versions/comments及全部Comment历史bucket、communications/automated_messages/attachments/assignments。Communication按权威ID检查全部私域根，重建可读附件JSON；再由存活行重建user_info。Shared只读者不见历史用户、访问记录和未审查可选timeline历史。正式Comment聚合保留原生父授权，不错误要求另有Comment REST角色。无name read probe返回False，有name真实文档hard-deny。 |
| Comment/Communication写入 | 所有私域根同时要求当前活动write与原生write；检查新旧根集合，不能删timeline链接洗白既有历史。reference/owner不能移换；Communication在controller validate后复核。Lead/Deal正式沟通仍沿原生父read、作者编辑和角色规则，不新授角色。 |
| ToDo / get_assigned_users | 旧allocated_to/assigned_by/owner本身不授予私域历史权限；读取description、ID、docinfo.assignments和受派用户名都须当前所有活动根write。保留旧行；当前活动owner仍可关闭不再授权的旧assignment，但新建/变更受派人或description须接收人当前可写目标。 |
| 原始响应缓存 | 非Administrator受保护对象及父记录JSON去掉_comments/_assign/_liked_by/_seen/_user_tags/__onload；压缩reportview列同样去除。显式选择、过滤、排序这些字段拒绝，包括别名；_link_titles只保留当前可读权威对象。受保护run_doc_method/runserverobj默认拒绝，不放开任意controller RPC。原生缓存历史计数及未审查onload附加功能不可用，正文/明确docinfo仍沿审查入口读取。 |
| 关联候选 | CRM get_linked_docs、Desk linked_with、dashboard get_open_count重新按可读对象生成。 |
| Call get_call_log / add_note/task_to_call_log | 不复用跨请求cached_doc返回体；检查当前Call和已有子write；新建走当前会话正常save，不ignore_permissions。 |
| mentions / notifications | 未授权mention使保存拒绝，不产生新正文通知；既有通知不删，读取按当前全部私域根write过滤，包括通知source/comment间接链。 |
| File / Attachment Gallery | File子类before_insert/validate；upload在字节前检查。统一引用图覆盖Comment链、Communication主引用+全部timeline链接和多私域根；所有同URL旧别名取根并集且要求每根当前write，不能靠File owner或共享父旁路。禁止public/remote/url复用、detach/reparent/公开转换。get_filtered_attachments保留原生dt/dn/四元filters验证后逐File判权，元数据与字节同门槛。预检还覆盖私域内容hash的公共/远程别名。 |
| realtime / 删除feed | 所有Note/Task（包括Shared）以及有私域根的历史/File/Call抑制doc_update/list_update；私域Comment/Communication不发含完整正文的docinfo_update，私域Chat/Notification不广播new_message。普通无私域正式沟通保留原生推送。can_subscribe_doc对这些私域文档一律403，包括owner；无实时刷新或查看者名单，须手动HTTP刷新。普通Lead/Deal订阅仍原生。私域子类使用官方no_feed_on_delete抑制无可授权reference_name却含源ID的删除feed。普通Lead/Deal也经官方窄子类仅设该标志，不生成删除feed，保留原生保存、权限、关联、业务方法及普通父更新推送；不改删除快照持久化。实际框架删除及快照保留待验。 |
| Deleted Document | 所有身份（包括特殊Administrator的应用请求）均拒Note/Task、File、ToDo、通知、嵌套/缺根私域历史、残缺/不一致快照以及含不透明原始历史缓存的快照read/list/export/delete/restore。原对象已删或alias失效不能判为公开。普通File/ToDo/通知快照也因此不能在应用中恢复，这是明确首版降级，数据不删；不新增管理员豁免。直接正式父历史快照须当前父read，无私域和不透明历史缓存的普通父快照仍原生。官方restore及bulk_restore均override，bulk先全量预检再调用原生，混合私域项403且不产生部分恢复。受控运维备份恢复另行验证。 |

`frappe.desk.notifications.get_open_count`保留原生dashboard关联规则的internal names/count与external count/open_count；**不执行DocType模块的任意get_timeline_data回调**，因此依赖该可选回调的Desk额外时间轴片段不受支持，原生CRM主时间线使用单独activities override。需真实UI确认固定版本实际受影响部位，不把缺片段当成功。

受保护类型全表授权扫描最大2000行（每类型），取2001确认超限；不截断授权集合，超限整请求拒绝并返回`team_access_limit:2000`。统一`references.private_roots`遍历历史主引用、Communication全部timeline链接及嵌套链，文件同URL别名合并所有根；半空/缺失私域或历史对象、环、路径深度达到12、每次遍历超过2000个不同节点、每记录超过2000条链接、超过2000个URL别名、图库/通信响应超过2000行均fail closed，可能返回通用403而不是伪空或截断。历史访问统一要求**每个私域根当前write且原生write**；Shared仅当前正文read。没有跨请求权限缓存；多别名×图遍历成本和真实容量性能未测，大数据前须重评可索引ACL，不能提高常数冒充可扩展设计。未知受保护RPC拒绝；未来版本/app/whitelisted方法须重新审计，不宣称约束任意第三方get_all。

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
5. `bench --site crm.localhost clear-cache`，重建所有Python/worker/调度/socket服务及前端到同候选镜像，不能只更新backend。**所有socket服务必须真正重启并确认旧连接/room清空；未经重启不得安装验收或解除维护。Python override不能驱逐安装前已加入Node的room；仅clear-cache/重新登录不足。** 核验静态JS、所有服务installed app及官方override实际生效，maintenance内先只读预检。
6. 双Sales User脚本、真实原生UI/独立页、匿名/无角色、CSRF、导出、附件、缓存与重启矩阵全过，再提交独审并解除维护。任何一项失败仍是MVP阻断，禁止将编译/管理员ORM等同验收。

### 安全回退

不能直接切回缺team_access的旧镜像，不能uninstall-app、删字段或停hook（before_uninstall明确拒绝）。安全回退镜像必须保留本版或经审查兼容的安全app及全部hook；维护模式下可关闭管理页/新写入，但不可关闭读权限边界。修复失败保持维护/停止服务并保留数据，不以开放旧API“恢复可用”。如确需完全撤掉app，先将私域正文、历史、通知与文件在隔离恢复站点作经过授权的安全迁移/验证，另行评审，不自动执行。全量恢复只能恢复到同一安全扩展版本并验证；备份成功不代表恢复已通过。

## 6. 双真实Sales User重复核验

驱动`apps/team_access/verify_http.py`使用标准库HTTP、两个独立Sales User CookieJar、真实密码会话和CSRF；不调用docker/ORM/Administrator，不创建用户、不改角色/User Permission，只创建带唯一M8前缀的**新合成fixture**。只修改manifest中经owner+前缀核验的M8记录，不改M5/M6/M7。凭据通过getpass或进程环境`TEAM_ACCESS_PASSWORD_A/B`，历史准备维护会话使用`TEAM_ACCESS_PASSWORD_HISTORY`；不打印、不落manifest、不提交，不放命令行、shell history或日志。manifest只有合成ID/marker及核对用账号名，放app忽略的`.local`。

仅在tower窗口内，用两个既有且无管理角色的Sales User。完整旧旁路回归**必须在首次安装前**prepare新M8 fixture：旧DocShare授read/write只用于复现，不是修复。`history-prepare`由既有非Administrator System Manager维护会话，在Note/Task各建Assigned/Info/Like/Workflow独立marker和primary私域、timeline共享Lead的Communication（Other，不发邮件）。固定上游未向Sales User授Comment create，不为测试新增生产绕权API。安装后仅history-prepare可对新M8对象临时显式授权维护账号并在finally撤回；缺原生write/父read则失败，不加角色/自动共享。

`legacy-prepare`**只允许未安装Custom Field的M8对象**，否则拒绝：在主Note/Task各建allocated_to=B的旧ToDo私密description；另建两条独立Private活动和primary共享Lead、仅timeline链接这两个私域根的Communication；创建其下private File及B拥有、挂共享Lead的同URL旧别名，先用B真实下载复现旧旁路；再建普通父private附件作正例。只用新合成数据，无public私文、不发送邮件、不改旧业务对象。安装后禁止伪造这些旧行；需隔离首次安装回归环境重跑，不关闭hook或uninstall。

```sh
python apps/team_access/verify_http.py prepare --user-a <SalesUserA> --user-b <SalesUserB> --fixture apps/team_access/.local/m8-run1.json --legacy-shares
python apps/team_access/verify_http.py history-prepare --user-a <SalesUserA> --user-b <SalesUserB> --history-user <ExistingMaintenanceUser> --fixture apps/team_access/.local/m8-run1.json
python apps/team_access/verify_http.py legacy-prepare --user-a <SalesUserA> --user-b <SalesUserB> --history-user <ExistingMaintenanceUser> --fixture apps/team_access/.local/m8-run1.json
# tower/M9：备份、预检、安装候选、所有服务含socket安全重建并清旧room
python apps/team_access/verify_http.py verify --user-a <SalesUserA> --user-b <SalesUserB> --fixture apps/team_access/.local/m8-run1.json
```

脚本只输出固定PASS/FAIL，不输出响应体/异常堆栈。每次完整重跑使用新manifest；拒覆盖已有准备、已有history/legacy_graph。部分失败保留新合成记录供受控定位，不自动删除，也不在同fixture盲目重试；先确认临时协作者撤回。verify首次会附着文件和创建历史，不能重复跑旧fixture并将状态差异当权限故障。缺旧DocShare/ToDo/URL别名任一fixture明确失败，不能把部分通过称完整验收。

自动矩阵保留双向Private detail/REST write/list/native getdoc/count/search、CSV普通/selected、父activities/候选、Shared当前正文只读/过去Version拒绝；Note/Task四Comment历史bucket与跨父Communication ID/marker，owner/协作者正例；Shared-only Comment/Communication native make/REST创建和私域timeline旁路拒绝、owner/协作者创建编辑正例、他人作者/撤权后/旧新reference移换拒绝；协作者和Task assignee正文写/禁止再授权/撤回、父权限撤回恢复、DocShare新建拒绝、正式父Comment聚合/只读父读者创建和自己编辑正例、不可见父拒绝、mention/notification；File私有下载/public insert或转换/detach/remote/未挂载URL复用/先公开后挂载/带附件发布拒绝。

R2新增：父getdoc/get_docinfo/get_communications（Private和Shared）隐藏私域Communication正文/ID/附件，owner正例；旧ToDo直读/list/Shared docinfo.assignments和get_assigned_users拒绝；旧B-owned同URLalias直读/list/字节和dt/dn图库元数据拒绝，普通父附件图库可见；timeline-only两根交集、只授一根拒绝、全授正例、同会话撤一根立即拒绝；owner及Shared-only都不能订阅私域，普通父can_subscribe_doc正例；显式读_comments拒绝。

**仍须人工/补充真实HTTP**：v2详细矩阵、原生CRM动态编辑器提示和管理页视觉、Shared写按钮反馈、Call动态链接/已有子更新、转换Lead/Deal通信排序/重复与父撤权、自动Email引用及timeline链接、get_docinfo全部顶层字段和原始缓存/_link_titles、Version直接detail与CSV、Data Import/Data Export全部变体、File先无父后挂载/remote/multipart/间接Comment链附件、匿名/无角色/CSRF、用户权限缓存撤回和重启、M5/M7兼容、备份恢复。仅对**新M8合成Lead/Deal**核验实际删除、原生权限/关联检查、快照保留及无删除feed，绝不删除M5/M6/M7既有对象；普通正式沟通与父订阅正例也必须保留。SM及受控Administrator的Deleted Document详情/list/CSV/单批恢复负例和普通父快照恢复正例详见第8节。新增**真实socket硬门槛**：全socket重启后owner也不能doc_subscribe/doc_open私域，open/close/disconnect无私域doc_viewers；普通父订阅正例、B先订阅共享父后撤销协作者再由A新增/改Comment/Communication/File/Task，不收到私文、标题、私域ID/操作者，HTTP刷新仍正确。驱动不含socket客户端；不新增依赖，不能用can_subscribe_doc HTTP403代替真实socket验收。最终MANUAL REQUIRED仍是验收阻断。

## 7. 验证台账（交付时持续更新）

| 项目 | 当前证据 |
|---|---|
| 固定上游源码审查 | R2使用M9自有network=none探针导出的Document/handler/API v1/v2/assign_to/load、各controller、Node订阅及delete_doc/Deleted Document schema+restore、完整CRMLead/CRMDeal源码；来源与SHA见M9的supplement-manifest-M8R2.json、supplement-manifest-socket-M8R2.json、supplement-manifest-controllers-M8R2.json、supplement-manifest-delete-doc-M8R2.json、supplement-manifest-deleted-document-M8R2.json、supplement-manifest-lead-deal-M8R2.json。无共享实例HTTP/DB/浏览器。 |
| Python/JS语法与diff检查 | R2及父删除兼容小修已过：19个Python文件AST、pyproject TOML、git diff --check（仅Git CRLF提示）、verify_local.py更新后的--help；两个未再改动的JS node --check和verify_http.py --help沿用R2通过结果。无新增依赖。 |
| R1既有离线证据 | 两活动×Comment/Communication创建/编辑/旧新目标/owner/原生write；四bucket与用户清理；probe False/hard-deny；自动timeline引用/移除拒绝；权威通信ID、转换Lead权限、重复/降序/limit21；原生update_comment guard。历史准备临时授权finally撤回成功/失败已用替身核验，不是真实HTTP。 |
| R2可重复本地回归 | `python apps/team_access/verify_local.py`无Frappe/DB/网络、只用标准库替身，默认10组PASS。已过多根/timeline/nested/Native write/revoke、旧ToDo、父docinfo/automated_messages/user_info、旧File别名与dt/dn图库/hash预检无写、raw缓存/压缩表/链接标题和guard、旧新图/环/悬空/半空/深度/边界、源端通知抑制/普通正式正例/所有身份私域订阅拒绝、父controller仅标志覆盖/继承方法不变/普通通知保留、所有身份快照详情/list/query/单批恢复及混合批全量预检，以及HTTP驱动8 bucket+2通信/旧ToDo/双根foreign-owner别名准备与重复/安装后拒绝。加`--upstream-root <M9公开证据根>`共12组PASS：执行固定CRMTask实际assignment方法，加载完整Lead/Deal class定义验证所有方法identity继承，调用固定实际insert_feed确认原始父负例仍拒、两个父子类只跳过feed。快照持久化与原生框架CRUD未执行；所有这些不是安全安装、真实HTTP或socket通过。 |
| 标准候选构建 | M9仅旧组合746076b/509df32报告标准build与network=none probe通过；其后File/R1/R2均待新exact-tip统一重建，不沿用旧结果。Windows未安装flit_core或新增依赖。 |
| 两Sales User真实会话 | 尚未获窗口，未执行；所有R1/R2 HTTP矩阵仅已编写，不记通过。 |
| 安装/迁移/预检 | 真实行为未执行；由M9负责。离线预检无自动搬删/无DB写；controller/API冲突全部拒绝。全socket重启清旧room是硬门槛。 |
| UI/CSP/PWA/真实socket/重启 | 全部未执行，不可豁免。 |
| 独立审查 | R1修复tip a743fca的R2为p1-4items/hold（父docinfo、dt/dn图库、timeline-only File别名、多历史ToDo）；本轮集中修订待新exact-tip复审，未获通过。 |
| 规模/性能 | 2000行/节点/边及深度12 fail-closed仅离线回归通过；负载和多类型递归成本未测，不适用真实规模上线。 |

## 8. D005-R2兼容降级决策链（2026-10-31 / Provisional，tower已授权）

- **问题和事实**：固定Comment/Communication.notify_change把完整as_dict正文发给父doc room；Document.notify_update发ID/操作者到doc/doctype room。Node只在join时通过Python can_subscribe_doc检查，撤权不驱逐旧room；doc_open/close/disconnect的doc_viewers还直接发users名单，无逐消息授权。这是源码确认，不是真实socket复现。
- **选项**：只限制新订阅不能防旧room；逐接收人当前授权推送/room重鉴权体验更好但固定官方扩展点不能安全替代Node内部；修改核心或全站禁socket超范围。选中**源端官方子类抑制私域正文和ID事件+对所有身份禁私域doc订阅+安装硬重启清旧room**，私域手动刷新，普通父与无私根正式沟通原生保留。Chat/Notification私域new_message只抑制推送，保留原生Sent通信对被回复通信的Replied状态写入；不跳过持久化。
- **Task assignment兼容**：固定CRMTask.validate在DB写入前调用原生assign，接收人仍不是存储记录当前writer，会被正确的历史门槛拒绝。官方ActivityTask保留固定validate中原生unassign在落库前执行，只把新assign移到on_update（落库后）；不能连unassign一起移后，因为原生remove会清DB assigned_to并对旧受派人生成通知。保留after_insert和原生assign/unassign内部业务路径；旧受派人移除通知生成时仍须目标旧授权有效，既已合法生成的通知无法事后收回。不用pending ACL、新增ignore_permissions或绕过历史校验。旧ToDo关闭不产生新description，允许当前owner关闭；产生新副本仍要求接收人当前write。需真实新增/变更/撤回assignee及通知持久化回归。
- **删除快照追加裁决**：固定schema向普通System Manager授Deleted Document read/export/delete，restore仅检查SM后直接读完整data，bulk_restore直接调用模块内restore并逐项commit；只override单恢复不够。选择保留数据、两入口预检、列表/详情/导出统一失败默认拒绝，不禁止所有私域删除、不放宽Administrator应用读取；Note/Task等直接拒，File/ToDo/通知及不透明缓存/嵌套/缺失根无法证明当前授权时保守拒。普通此类快照也不可应用恢复是已批准代价；无不透明历史缓存的普通父快照和当前父可读的直接正式历史保留原生。私域no_feed_on_delete避免删除后生成半空引用且含源ID的feed，不改快照持久化。
- **普通父删除兼容追加裁决**：已用固定实际insert_feed调用确认原生Lead/Deal默认删除feed被半空引用guard拒绝，固定完整CRMLead/CRMDeal均无该标志、on_trash或after_delete。拒绝放宽半空Comment、信任客户端Deleted字段或改核心。tower授权的最小方案已实施：`parents.ActivityLead/ActivityDeal`仅设官方no_feed_on_delete=True，全部原生方法、权限、关联检查、保存和普通更新推送继承不变，preflight同时拒绝controller覆盖冲突。代价是普通父也不再产生删除feed；快照流程未改，真实保留待验。离线对完整固定父class的全部方法identity及实际insert_feed路径回归已过，不是整个delete_doc事务通过。带附件/关联阻断、真实删除/快照仍须核验，仅使用新M8合成对象，不改删M5/M6/M7对象。
- **Administrator精确语义**：原Note/Task等继续已有受信特殊`Administrator`分支（permissions.permitted中的早期True及has_permission跳过），依据本页第1节D005暂选；普通System Manager/Sales Manager不因此有私域旁路。本轮未反向改变该既有策略。新增Deleted Document分支在该早期True之前执行，应用guard/query/单批恢复不豁免Administrator；私域socket订阅同样全身份拒绝。受控运维备份恢复不是网页快照自动权限。
- **置信度/验证**：中等；固定源码链和可重复替身通过（含所有身份快照读/列表/单批恢复、混合批次无副作用、普通父正例、父controller原生方法继承及实际insert_feed），真实framework/controller选择、Node经HTTP override拒订阅、真实旧room/撤权/重启、删除/快照恢复/通知持久化和UI兼容均未验证。SM真实HTTP须额外覆盖快照详情/list/selected CSV、单恢复403、混合批恢复403且公共项未恢复、普通正式父快照按原生恢复正例；特殊Administrator应用拒绝另作受控核验，驱动不登录Administrator。所有门槛保留，未宣称实时边界关闭或MVP通过。
- **可逆性/安全回退**：无核心或schema额外改动，无新依赖；仅回退到保留同等读权限边界的经审查兼容app。不能直接去掉子类、关hook、恢复原生私域推送或切无扩展旧镜像；失败保持维护。恢复细粒度推送须先证明逐消息当前授权和撤权旧room安全。
- **复评条件**：官方出现接收人授权/room驱逐扩展点、上游版本变化、团队必须实时协作、性能越界或任何真实正负例失败。当前无新增用户决策卡点；tower允许此可逆降级，不能用文档代替真实验收。

当前无新增需要用户决定的技术卡点；D005是可逆暂选。真正阻断是部署窗口、真实全边界核验和独审，不用架构文档替代可观察权限证据。AGPL对应源码及修改说明须随网络服务履行适用义务，本页不构成法律意见。
