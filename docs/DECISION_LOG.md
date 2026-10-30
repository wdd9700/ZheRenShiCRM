# DECISION_LOG.md｜技术与产品决策链

> **过程文件，不是一次性总结。** Agent 在做出较大的临时决策后立刻记录，再沿临时决定推进；交付时必须回看全链。  
> 创建日期：2026-10-31  
> 当前状态：D-001团队方向、D-002基座暂选、D-003派生镜像修复均已留过程记录；**可登录CRM基座及合成Lead写读烟测通过，完整团队MVP未验收**。保留初始记录并在相应条目追加实测，不将早期未知状态当最终结论。

## 用法

- 编号：`D-001`、`D-002`……，保持唯一且不因反悔而复用。
- 状态：`Provisional`（已暂选）、`Validated`（已通过约定验证）、`Superseded`（已被新决策替代）、`User Decision Needed`（确需用户决定）。
- **记录时间点：决策刚发生后、继续推进之前。** 不等到交付时补历史；可在原条目追加后续验证和交叉链接。
- 低置信度不等于阻塞；正常可回退决策不应无故推给用户。
- 变更选择时写一条新记录引用旧 ID，不删除历史。

## 决策索引

| ID | 日期 | 主题 | 状态 | 临时方案 / 待选 | 复评条件 |
|---|---|---|---|---|---|
| D-001 | 2026-10-31 | 团队集中服务端与跨端路径 | Validated（方向） | Web/PWA 优先；单用户仅最小测试 | 用户方向变化；真实跨端体验反馈 |
| D-002 | 2026-10-31 | CRM 基座与可回退部署 | Provisional（直接镜像部分由D-003替代） | Frappe stable谱系；Twenty备选 | 业务/权限/恢复实测不满足 |
| D-003 | 2026-10-31 | 官方镜像缺应用的派生构建 | Validated（本地基座烟测） | 固定Framework基底+CRM源码commit | 业务/权限失败，或完整官方镜像可用 |

### D-001｜团队为架构前提，跨端先复用 Web

- **日期/状态**：2026-10-31 / Validated（仅需求方向，不代表实现已验证）。
- **触发与目标**：用户最新明确要求面向团队、集中服务端与跨端客户端，优先低迁移成本；旧稿“先单用户后团队”不再是架构约束。
- **已核实事实**：tower 方向广播及 M1/M2 报告确认该更新；Electron 不覆盖 iOS/Android；本机没有可验证 macOS/iOS 原生构建签名的环境。
- **候选与取舍**：一套响应式 Web/PWA + 集中服务端（复用基座，先选）；Electron/Tauri 桌面薄壳与 Capacitor 移动薄壳（确有原生需求后评估）；四套独立原生端（当前成本高，暂缓）。
- **决定/置信度**：团队身份、私域/共享权限是第一阶段验收门槛；Web/PWA 为暂定低成本客户端路径。方向高置信，四端体验与薄封装可行性中低置信、未验证。
- **边界/回退**：不承诺四端安装包；单用户只作最小烟测，不替代双账号 UI/API 越权验证。客户端不嵌共享管理员令牌；真实私域数据未授权不得进入演示。
- **证据与下一步**：M1 官方能力调查、M2 本机工具调查；后续验证桌面/移动 Web、团队账号、拥有者/经理规则和私域隔离。
- **复评/用户决策**：普通可逆选型无需用户拍板；真实资料共享、公网开放、付费原生分发等授权另行确认。

### D-002｜条件首选 Frappe CRM stable，独立本地沙箱，不把开发 Compose 当生产

- **日期/状态**：2026-10-31 / Provisional；记录于部署实现之前。
- **触发与目标**：优先复用 CRM 跑通“导入→联系人/企业→需求→商机→沟通→跟进→时间线”，为团队保留安全可回退基线。
- **已核实事实**：已读取 M1/M2 完整调查。M1 官方调查认为 Frappe stable main v1.x 的 Lead/Deal、Activity、Task 最贴近闭环；develop 为 v2 不稳定。官方生产文档采用 stable easy-install；仓库开发 Compose 含 latest 与样例密码，不能直接作为交付基线。
- **候选与取舍**：
  1. Frappe CRM stable：现成业务链与 Framework 权限/API/备份，首选；中文导入去重、CEO 私域、复杂对象新 UI、恢复尚未实测。
  2. Twenty stable：对象扩展、导入治理和 OAuth 较强；扁平中文表需拆分，行级权限为 Organization Premium（自托管也如此），多态关系导出受限，暂为备选。
  3. 从零开发：当前没有证据证明值得放弃现成业务逻辑，暂缓。
- **许可证**：Frappe CRM AGPL-3.0；Frappe Framework 为 MIT（须按固定源码再核对）。Twenty 主体 AGPLv3，部分包 MIT、Enterprise 标记文件商业许可。修改后网络服务需评估 AGPL §13 对应源码义务；不将团队内网等同免除义务；本记录不是法律意见。
- **临时决定/置信度**：首选官方 Frappe stable 发布谱系，后续锁定具体 CRM/Framework 版本、上游配置提交及镜像 digest；独立项目名/持久卷，只绑定 127.0.0.1，不改主机服务。基座中置信，部署低置信（尚未容器启动）。
- **初始运行证据**：Windows Docker 29.3.1 客户端存在但 docker_engine pipe 缺失。经授权只读进入已有 Ubuntu-24.04，默认 uid=0、WSL2 kernel 6.6.87.2，Docker socket 存在且服务 active，54GiB RAM / 根卷819GiB空闲；未安装软件、未 sudo、未修改系统服务。内部 CLI/版本仍在核验，不能仅凭 socket 声称可部署。
- **可逆性**：仅合成数据、独立卷；停止容器不删卷。更换基座前导出保留来源 ID 的中立 CSV，并备份数据库及公私文件，在同版本新站点恢复验证；不使用 down -v 作为回退。
- **未验证边界/复评**：镜像能否拉取、健康/登录、中文六列导入幂等与错误行、团队 UI/API 隔离、重启持久化、导出关系、备份恢复均未通过。任一核心条件不满足则重新比较 Twenty，不无限堆自定义补丁。
- **用户决策与后续授权**：普通本地隔离沙箱无需业务选型审批；扩大网络暴露、使用真实资料、付费 Premium、不可逆迁移仍需明确授权。初始只读/root限制已由用户经 tower 的最新授权覆盖：第一个 Ubuntu-24.04 为实验环境，允许本项目 root Docker 部署及必需的 Compose 安装；不碰第二个训练发行版、不删数据/卷/镜像、不改 Docker 服务或用户组。当前没有必须再交用户决定的业务选型卡点；网络可达性是操作阻碍，不是新审批要求。
- **后续验证（2026-10-31）**：已安装授权的 Ubuntu 官方签名源 `docker-compose-v2=2.40.3+ds1-0ubuntu1~24.04.1`（唯一新增包、14.8MB下载/66.6MB磁盘；未改系统服务）。官方 GitHub Compose v5.1.1 项目本地下载超时，未执行未校验文件。Docker Hub不可达后以 Amazon ECR Docker Official Images公共镜像源拉取Framework v15保守依赖MariaDB10.6.28/Redis6.2.24-alpine并固定RepoDigest；对应新隔离v15项目DB健康、两个Redis PONG实测通过；旧11.8/8.6项目亦健康且卷保留，但不算v15兼容性证明，无发布端口。CRM stable digest大层经900s/600s拉取未完成；后续核对v1.90.0独立发布tag digest与stable不同，改锁发布tag digest而不声称二者一致；Framework精确运行版仍待镜像可用后的bench version。CRM登录/健康/合成数据闭环尚未通过，MVP未完成。配置、运行命令、完整digest及阻碍见 `deploy/README.md`。

### D-003｜官方CRM发布镜像缺应用，改用固定源码派生镜像（替代D-002的直接镜像部署部分）

- **日期/状态**：2026-10-31 / 构建前Provisional → Validated（仅本地基座烟测，验证追加见下）；Frappe基座选择不变。
- **触发与已验证事实**：精确v1.90.0 OCI index c3873...通过标准skopeo完整复制（19 blob哈希全部一致）及docker load；实际apps仅frappe15.125.0，Python find_spec(crm)=None；new-site安装Framework后install-app crm报ModuleNotFoundError。[发布workflow固定commit](https://github.com/frappe/crm/blob/36bd8859f2a6345a620477bc708d0546e8c3f08a/.github/workflows/builds.yml)传旧APPS_JSON_BASE64 build-arg，而[已核对layered Containerfile固定commit](https://github.com/frappe/frappe_docker/blob/61d35da827ebc04d01b64c9e78385597ccebc9d8/images/layered/Containerfile)只读apps_json BuildKit secret、不接收该ARG：接口不匹配是源码事实，造成此发布镜像缺app是高置信因果推断（发布workflow未固定frappe_docker checkout，未还原当次CI全部日志）。未对外提交issue。
- **候选**：继续用缺应用镜像（不可行）；切旧未知完整版本（仍要验证且丢当前稳定修复）；以已验证不可变Framework镜像为基底、补入固定CRM源码并构建资产（暂选）；转Twenty（保留，但此故障是打包而非业务不匹配）。
- **临时选择**：只在deploy/增加派生Dockerfile，基底固定c3873...、CRM源码固定v1.90.0对应commit `36bd8859f2a6345a620477bc708d0546e8c3f08a`；以本地构建镜像ID锁运行，禁止移动tag悄然更新；不改上游、不删已建Framework站点/旧卷，成功后在现站点install-app crm恢复。依赖/资产实际构建及运行仍待验证。
- **置信度/边界**：中；Framework与CRM谱系来自官方已核对版本，局部部署修复可逆，但构建依赖网络和原生资产仍未知。代码仍为AGPL-3.0；保存源码commit及构建步骤，不将修复打包当业务/权限完成。
- **授权/回退**：第一个实验Ubuntu、项目级root Docker与必需构建工具/现有7897单进程代理均已获tower转达授权；不改系统代理或daemon，不触碰第二发行版、不删任何卷/容器。失败保留原官方镜像和已建站点，不生产迁移。
- **复评/下一步**：派生镜像需import crm、bench version、资产构建、真实登录/健康通过才接受；构建复杂度失控或业务验证失败重新比较Twenty/完整旧稳定版本。详细结果追加deploy/README.md。
- **构建验证追加**：固定源码与上游两份yarn.lock未变化断言通过。host网络下Framework默认Redis 127.0.0.1:13311超时；仅资产RUN改为network=none后按官方离线容错路径成功（Vite3315模块/PWA/翻译，16.5秒），未引入构建期数据库。import crm1.90.0、bench version crm1.90.0/frappe15.125.0通过；派生产物ID `sha256:2408974e8c5b8f3feacbaf6cac3c62e69c41fe1cf10dec251dd6cbdd1b9de5f3`。Node peer依赖/大chunk警告未改上游；Python依赖尚非逐包hash锁定，不声称字节级复现。
- **运行配置保护追加**：获tower批准只重建无状态configurator，旧可写层仅pycache；旧image与退出0及logs/sites挂载均记录。重建后site_config SHA256完全不变、运行common中的db/Redis连接仍完整，apps.txt新增crm，未写空站点配置。另一次诊断误用无名docker run --rm，自动清理其自身容器/匿名卷，已报告越界并停用；无项目命名卷/业务资料受影响，后续探针全部固定命名保留。

- **最终烟测追加**：原站点install-app crm成功exit0；9长驻服务运行，DBhealthy、两Redis PONG，bench version已在运行容器再次核验。WSL与Windows真实pong/Administrator登录会话/CRM HTML+JS资产通过；合成REST/CSRF Lead `CRM-LEAD-2026-00001`写读、重复烟测复用同ID通过。D-003可接受为本地基座部署修复；D-002仍须业务/团队权限/恢复验证，不是完整MVP完成。详细前后site_config哈希、授权保活到期、一次探针越界及残留资源见deploy/README.md。
- **D-002后续纠正**：前段“Framework待测/网络失败/唯一新增包”是早期时点记录；当前Framework15.125.0已测、标准skopeo代理下载成功，另经授权安装skopeo+依赖与Buildx（固定版本见README），未改系统服务/全局代理。新增8小时有限WSL保活是获批临时开发保障，生命周期根因未证实；非生产部署方案。

- **独审R1交接修复**：唯一P2指出忽略运行材料仍绑定临时wt-3，原文档长期使用该路径的建议不成立。选择显式本机`handoff-runtime --target-dir`，目标必须先有合并后匹配的跟踪代码及忽略规则；私有`.runtime`存放两文件，原子不覆盖复制、保护ACL、源保留、正文/摘要不输出，自动目标check/smoke。采用专用私有目录而非收紧整个deploy/递归ACL，保持团队代码和WSL访问边界。预合并仅演练私有fixture；合并后主checkout实际交接、Windows/WSL验收及tower确认是清理wt-3前强制门槛，未执行前不得称迁移完成。不生成新密码/站点、不删源或改主checkout产品代码。实现和验证见deploy/README.md。
- **R1修复验证追加**：最终工具在私有Git fixture真实复制后，目标Windows和第一Ubuntu的check/smoke均通过；目标Ubuntu status仍见原项目。重复调用不改字节/mtime，公共deploy ACL不变；冲突、未忽略/已跟踪、代码/路径异常、硬链接与正常/断裂junction、不安全目标ACL及父DeleteChild均拒绝。显式仅保护专用目录后WSL可读；Git CRLF代码和含空格路径亦真实通过，运行材料不转换。源保留、凭据正文/摘要未输出，无新增用户决策；实际主checkout交接仍未执行，须合并后按README门槛完成。

- **标准登录阻断与资产修复（M7回查）**：此前API密码登录/CRM Vite资产烟测遗漏Framework标准/login；浏览器实际请求裸`/frappe-web.bundle.js`404，jQuery/frappe.login未加载，表单退化GET。M9隔离network=none探针证实原base c3873的根assets.json有32键且目标hash文件存在，但sites/assets/assets.json不存在；M7 36a89两manifest均{}（M8未加入）。原D003 Dockerfile直接CRM-only build未preseed根manifest到sites/assets，esbuild无Framework入口后写{}，随后cp覆盖根manifest；M7原样继承该段，不能归咎M8。临时DOM改POST/name或注入sid不算标准登录验收。选择构建前复制官方既有assets到sites/assets，保留官方映射与hash产物，构建后强断言关键映射、原键不丢且目标文件存在；不手工映射、不重编Framework、不改上游。smoke增加Guest登录页JS/CSS及Content-Type检查；新干净tab正常表单登录→CRM/导入仍须独立浏览器验收。修复镜像由M9单一操作者先构建M7-only，部署仍需tower窗口，未验证前保持阻断。

### D-004｜受认证六列资源导入扩展（M7）

- **日期/状态**：2026-10-31 / Provisional，实施前记录。
- **目标/已知事实**：用户要求真实网页上传、预览、确认及逐行结果。已读M5实际源码与MVP_WORKFLOW；原生导入一次只写一种实体、无自然幂等；Lead.organization实际为Data，需求/原文需additive字段。运行源码Frappe15.125.0/CRM1.90.0 www及CSRF已核验；实际角色限制仍等M6交接。
- **候选**：原生单对象导入（不能覆盖六列跨实体）；浏览器逐条REST（事务/并发/权限不可控）；最小Frappe app `resource_import`（暂选，复用ORM/认证/原生www，无额外依赖）。不改Vue、不启用Server Script。
- **决定/理由**：服务端单一解析计划写入；权限过滤候选、显式关联消歧、完整SHA256唯一键；站点数据库命名锁在最终commit之后释放、每行savepoint异常先回滚，防并发重复和孤儿。锁仅覆盖本app，不宣称阻止上游原生手工竞态。
- **原文/回退**：Lead保存需求/产品/联系方式/来源与六列快照、实体Link；版本化迁移只增缺失字段，不覆盖既有字段。保留旧镜像与备份，需协调M6停写窗口才共享部署。不删字段、不uninstall；旧镜像若缺已安装app不可直接启动，须使用仍含app的兼容回退镜像。
- **置信度/证据缺口**：中。具体契约和纠正M5截断SHA1、异常处理、破坏回退风险见 `IMPORT_APP.md`；真实HTTP、并发、权限、原文和视觉尚未验证。未声称完整MVP/恢复完成。
- **实施中M6证据修订**：Organization/Contact对Sales User默认广泛开放；Lead按owner/分配过滤，Manager全读；FCRM Note无父权限继承。因此入口收紧仅System Manager/Administrator、不写Note、不把产品原文写Organization；原文只保存Lead。姓名/解析联系值同样可能私密，页面必须独立默认不勾选的共享确认，preview/apply均验shared_consent；不接受共享则明确阻止，未支持仅私域Lead模式。本轮只用合成数据，管理员导入不等于团队私域问题已修好。
- **实施实证修订（原文与receipt）**：Frappe Document._sanitize_content会清洗Long Text中的HTML；经tower批准只增5个Code verbatim字段作为产品/需求/联系方式/来源JSON/六列JSON权威原文，保留早期5个Long Text但新导入不写、不改类型/删列、不全局ignore_xss_filter，共14字段（Lead13+Contact1）。历史导入缺verbatim返回人工核验错误，不自动覆盖、不冒称原文完整。Code存储不等于HTML可安全显示，网页坚持textContent并验真实浏览器。本站无encryption_key导致签名preview500，改现有Redis15分钟256-bit不透明receipt，只存user/session/source/完整文件digest/共享确认，不存CSV；apply重新校验身份、权限、内容与候选。篡改/跨会话/丢失/过期fail closed，receipt期内可幂等重试/并发，最终防重仍由DB唯一约束+锁负责。
- **会话撤销错误响应修订**：M6禁用合成System Manager后，原会话有效receipt的apply由Framework拒绝417、业务零写，但响应含完整exc堆栈，原安全断言FAIL。只读固定v15.125.0源码证实Session.resume.validate_user在HTTPRequest构造时抛ValidationError，早于app handler及before_request/auth_hooks，故导入局部disable_traceback不能覆盖。官方System Settings.allow_error_traceback默认1，get_system_settings只读该站点DB单例而非site_config。tower选择在M6独占窗口记录单一旧值、正常保存为0、clear-cache，回退恢复该旧值；新站点部署亦须显式配置。备选app after_request错误normalizer暂不采用，避免扩大自定义拦截；不改核心、不盲重建镜像。
- **安全断言与日志边界**：官方V1 report_error无条件保留exc_type，纯ValidationError类型名不是堆栈，tower明确允许；仍禁止exc/exception堆栈、文件路径/行号、调试内容、候选及私密正文，不静默抹掉历史FAIL。关闭会跳过report_error的errprint，其request-local错误列表与条件stdout输出会减少；>=500独立log_error_snapshot（有异常排除规则）及已启用的请求访问日志不由此开关关闭，417本来无持久snapshot保证，不能称日志完全不变。官方证据及可复现步骤见deploy/README.md；配置修复、角色撤回与视觉最终结果待M6独立回传，尚未标Validated。
- **后续独立证据与当前阻断**：M6最终12API负测PASS（含disabled417无堆栈、角色撤回403、匿名/跨用户、业务零写），原设置1→0且账号恢复。首次正常save因既有language/time_zone缺失拒绝且未提交，后M6以ignore_mandatory仅保存目标设置并clear-cache；不作为通用部署默认。tower临时已登录浏览器真实preview/apply得到M7VISUAL001成功1/重复1/错误1，危险script/img以文本显示；下载落盘、原生链接/移动视觉仍未验。标准/login因D003上述manifest丢失而失败，DOM改POST/name与sid注入不算登录验收；须修复后新干净tab正常表单登录→preview→apply。已实现preseed/构建强断言及Guest登录资产smoke，本地模拟覆盖正常、空映射、错Content-Type及外站资产拒绝，尚待M9真实镜像构建与部署窗口，M7仍blocked、不报完整MVP。
- **复评/用户决策**：普通可逆app与字段暂定无需用户审批；真实数据授权、公网暴露或破坏性操作另行决定。后续按HTTP/并发/双账号与视觉证据更新。

### D-005｜原生Note/Task私域权限补强（M8）

- **日期/状态**：2026-10-31 / Provisional，实施前记录；未通过仍阻断完整团队MVP。
- **触发/证据**：M6真实HTTP证实私密FCRM Note detail及PUT越权均200，未共享Note正文经activities泄露。M8固定源码核对：permission hook False后仍有DocShare OR，query hook后亦share OR；get_docinfo顶层响应、activity counts和mentions存在旁路。单permission hook不足。
- **候选**：A 在原生Note/Task新增默认Private、显式Shared可见性，覆盖多入口官方扩展（暂选，保留原生UI/历史）；B 独立私域对象（损失原生UI，须迁移，暂缓）；C 单permission hook（已被源码证伪）。不接受脆弱全局SQL补丁。
- **决定/边界**：Shared只有可读父Lead/Deal者可读；写仍按拥有者/明确授权协作者，不能把父可读等同任意写。任务assignee是明确协作但仍须父可读。Comment定义正式共享业务沟通，UI须提示；私文使用Private Note。不自动发布旧Note/Task，不改正文，不向外发数据。
- **置信度/验证**：中低；需双账号直接接口、列表、CSV、活动、通知、共享撤回及UI实测和独审。M7仍仅管理员共享商业对象确认，不因此扩权。
- **回退/风险**：不得关闭安全hook重新暴露已经存入的私文；保留安全包、关闭访问或恢复隔离副本。不删权限字段，不把部署成功等同权限完整解决。
- **复评/用户决策**：这是可逆安全修复暂选，不需等待用户审批；真实资料授权/数据迁移/删除或业务共享规则改变仍须用户决定。各旁路未全部实测通过前保持MVP阻断。

## 决策条目模板（复制到文件末尾，使用后删除本行提示）

### D-XXX｜[一句话描述实际要解决的问题]

- **日期/状态**：YYYY-MM-DD / Provisional
- **触发与目标**：这项选择用于解决什么当前业务/工程问题？
- **已核实事实**：仓库、版本、文档、实验结果或可重现的限制。
- **未核实假设**：不确定但目前暂时采用的前提。
- **候选方案与取舍**：
  1. A：好处 / 代价 / 放弃原因。
  2. B：好处 / 代价 / 放弃原因。
  3. C（如有）：好处 / 代价 / 放弃原因。
- **临时决定**：选什么；为什么选它而不是另外几项。
- **置信度与依据**：高 / 中 / 低；为什么。
- **风险、影响与可回退性**：影响哪些数据、模块、部署或许可；怎样撤销/迁移。
- **证据**：链接、命令、版本、测试记录及结果；未实测则直说。
- **下一步检验**：用什么可观察结果判断临时选择是否正确。
- **复评触发条件**：出现什么证据或业务变化需要改选。
- **用户决策**：无 / 需要；如需要，说明**为什么不能先自行做可回退临时决定**、不同选择将分别影响什么。
- **后续记录**：验证结果、关联决策 ID、最后更新时间。

---

## 交付时决策复盘模板

### 1. 做了什么
- [完成的功能、使用路径、测试结果、未完成/模拟部分]

### 2. 为什么这么做
- [关键 D-xxx、业务原因、实测证据、舍弃备选的理由]

### 3. 当前必须由用户决定的卡点
- [若无：明确写无]
- [若有：每个卡点的业务影响、用户需要选择什么、不决定阻塞什么]

### 4. 推荐但置信度较低的选项
- [包含已由 Agent 临时选择、仍需实测的方案；不等同于必须用户批准]

### 5. 推荐理由
- [每个备选的收益、风险、成本、证据缺口及复验办法]

### 6. 为什么一定要交给用户，而非自行临时决定
- [针对第 3 项逐条说明：不可逆性 / 数据授权 / 支出 / 法律与商业责任 / 用户价值偏好；若解释不成立，应由 Agent 暂选后继续]

### 7. 决策链状态
| ID | 最终/当前状态 | 已验证证据 | 尚需复评条件 |
|---|---|---|---|
