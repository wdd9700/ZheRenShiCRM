# Resource Import：受认证六列网页导入

状态：M7管理员合成导入闭环已完成真实验收，申请独审（2026-10-31）。管理员HTTP与M6最终12API负测通过；标准/login资产故障已修复部署，同一原生标准登录会话完成新CSV上传→preview→独立确认→apply、真实失败CSV落盘及三原生详情实点，390×844窄屏只读检查通过。保留历史417泄堆栈、资产404及初始化保存FAIL，不以页面壳/HTTP200冒充详情。维护正常save只修复三必需设置，当前遥测0/traceback0、有效时区不变、正常Skip完成，窗口已释放。无create专门负例仍未测，不称完整团队MVP/移动原生包/恢复完成。对应 M5 实际源码 `tools/crm/m5_import.py` 与 `docs/MVP_WORKFLOW.md` 第6节；后者是建议，不是安全实现。

### M6证据后的安全收敛（实施中即时追加）

M6已核对实际DocPerm/hooks：Sales User可广泛读写Organization/Contact；Lead按lead_owner/分配过滤，Manager反而全读；FCRM Note无父权限继承。因此入口现收紧为仅System Manager/Administrator，拒绝普通Sales User及Sales Manager，仍逐doctype核验read/create。不得声称是普通团队导入权限闭环。绝不写Note；产品/需求/联系方式原文只进Lead，连新建Organization也不写产品原文。

企业名、姓名和解析联系值本身也可能是私域资料：页面提供独立、默认未勾选的共享确认，明确创建/复用企业和联系人会对现有Sales User开放；preview及apply后端均必验`shared_consent`。不接受共享则明确阻止，当前不支持仅私域Lead模式。本轮只可合成数据。这个确认不是私域权限已修复的替代。

兼容回退：`deploy/Dockerfile.compat`从保留的旧CRM派生镜像补入app，使已安装app记录仍可加载；设站点`resource_import_disabled=1`关闭入口，再切兼容回退镜像。不直接切缺app的旧镜像，不删字段/卸载app。以下实施前条目中Sales Manager许可及Organization产品原文写入已被本追加替代。

## M7-D1 / Provisional：最小 Frappe app

目标：`/resource-import` 上传 UTF-8 CSV → 服务端逐行预览/错误/显式关联消歧 → 勾选确认 → 结果/失败CSV → 原生企业、联系人、Lead。只创建需求线索，不自动转换商机，无 AI，无上游 Vue 修改，无全局 Server Script。

备选：原生单 DocType Data Import 无法一次建三实体、无自然幂等；浏览器逐条REST无法保证权限与行原子性；扩展app复用Frappe认证、CSRF、ORM、www与迁移，当前暂选。纯标准库，无新增运行依赖。置信度中，待真实HTTP/并发与视觉验收。

已核对运行镜像 Frappe15.125.0 / CRM1.90.0 源码：CRM Lead/Organization 有 System Manager、Sales Manager、Sales User create/read/write；Contact 有 System Manager、Sales Manager、Sales User create/read/write（Sales Master Manager不能误写成Sales Manager）。实施前曾拟开放 System Manager / Sales Manager，已被M6实际权限证据替代为仅System Manager；仍逐DocType核验read/create，不赋新角色、不提权。

## 解析、权限与消歧

- 服务端唯一解析/计划/写入入口，客户端仅文件读取和文本节点渲染。
- 六列准确表头（可重排），最大1MiB UTF-8、500数据行、每格10000字符；严格CSV，不截断原文。姓名/企业/需求必填。微信等不透明联系方式原文可保留；语法提取数字/邮箱用于候选及新联系人解析字段，不能据此认定同一人，姓名+企业也只产生候选，不自动合并。
- 所有候选列表用 `frappe.get_list` 权限查询，返回的对象逐个检查read；不全表 get_all，不把不可读候选名称/详情放响应。已有联系人即便单一也需显式选择；不得在手机号/邮箱冲突时挑第一个。已有企业只精确名称匹配；用户须明确确认复用。不会修改复用联系人或企业（不偷偷增加关系或覆盖原文）。联系人与企业不匹配要求手工整理，不合并猜测。
- preview POST不建File、不写业务库；只在现有Redis写15分钟随机不透明receipt（不保存CSV原文），绑定用户、session、来源、文件完整digest及共享确认；apply必须确认且receipt一次绑定同一会话/文件/选项，服务端重新解析、重新做权限/候选计划。receipt丢失/过期/篡改/跨会话/跨用户均fail closed并要求重新预览；不能把receipt替换成另一份内容。调用者身份 `.insert()`，不使用ignore_permissions/set_user。进入应用handler后的错误仅返回固定分类，不泄露异常正文、SQL或堆栈；会话初始化等Framework前置异常另须配置官方站点错误响应安全基线，见下文。

## 幂等与事务（纠正M5建议）

- 完整SHA256，JSON数组编码避免分隔符歧义；版本+原始六列业务内容（序号除外）构成行身份，原文差异视作新资料。来源文件/行号不参与幂等，重复同资料不同文件仍同一需求。唯一索引 `CRM Lead.custom_resource_import_key` 兜底，不用截断SHA1或备注LIKE。
- MariaDB站点级命名锁包住apply全批，锁等待有界；获取后先结束旧只读事务建立新快照，逐行重新计划。全部成功/失败行处理后显式commit，再释放锁。不能在最终commit前释放锁，否则并发请求仍看不到记录。锁仅串行化本app，不声称阻止原生UI同时写联系人。
- 每行savepoint包住企业→联系人→Lead全部创建；任何失败先回滚该行再返回结果。唯一冲突也不直接跳过，否则会留下刚创建企业/联系人孤儿。Frappe15.125的savepoint不会回滚Python事务回调，因此同时保存/恢复before/after commit/rollback回调、realtime log及currently_saving，避免失败行在批次commit后发出已回滚记录的事件；此处依赖固定版本CallbackManager内部队列，升级须复核。应用异常整批rollback。进程中断数据库回滚并自动释放连接锁；幂等重试。
- 已导入Lead仅在可读时返回链接；若唯一冲突来自不可读对象只给通用失败，不返回其存在、ID或详情。所有返回链接均按当下read权限核验。
- 联系人新增使用完整SHA256自然键唯一字段（姓名、企业、原始联系方式），并在批次锁内重新查候选；不能保证第三方绕过app、不同联系方式表达或上游手工新建的自然人绝无重复，遇候选必须消歧。

## 持久字段与非破坏迁移

版本化 `schema.py` + v1/v2 patch + install/after_migrate hook，只新增缺失字段；已有同名不兼容字段时拒绝，绝不覆盖数据/删除字段。最终14字段：Lead的导入key、Contact/Organization Link三字段；Code类型的`custom_resource_{requirement,offering,contact,source,snapshot}_verbatim`五字段（后二者JSON）；早期五个Long Text字段保留但新导入不写；Contact自然key一字段。

实证：Frappe15.125会清洗Long Text含HTML原文，因此经tower批准向前增加5个Code字段而不改早期字段类型/删除；Code原文按纯文本渲染，不使用innerHTML。六列JSON解码须与输入逐字符相等。若历史key命中但缺verbatim，返回“历史资料待核验”错误要求人工确认修复，不静默覆盖、不声称历史原文完整。M7HTTP001在修正前preview500，尚未进入apply、没有业务行写入。Company产品原文不写共享Organization，所有每行原文以Lead Code快照为准。

字段不是权限模型，不将CEO私域数据转成普通共享字段。无需回填M5备注，也不假装自动升级旧M5资料。receipt期内可重用，重复与并发依赖数据库幂等；选项中的消歧选择在apply提交时服务端按最新候选/权限逐个重新核验，不信任客户端名称。缺失站点encryption_key不在preview生成/修改配置，改用既有Redis的短期receipt。

回退保留app安装记录/字段/数据，切旧镜像前需保证旧镜像能加载安装app（必要使用含app旧代码镜像）；不得删除Custom Field或uninstall-app。数据库恢复不是本任务已完成项。

## 部署与验收门槛

构建上下文改为仓库根，Dockerfile专用ignore只放行派生Dockerfile及app源；pip editable烤入镜像，无临时docker cp安装交付。构建与部署分离，禁止构建覆盖共享运行image.env；保留旧image lock与镜像，tower协调M6停写、备份数据库及公私文件后才安装/迁移/更新所有Python服务。未获窗口不执行共享schema/服务变更。

验收：唯一M7合成数据；真实HTTP匿名/无角色/无create/CSRF拒绝；preview无业务写入；正常/错误/同文件重复/跨请求重复/并发；原文与特殊字符；失败CSV与原生链接。网页视觉由tower协调，不把HTTP200当视觉验收。不声称完整MVP、备份恢复完成。

## 首轮已执行证据（历史时点；后续收敛见末节）

- 旧CRM镜像`sha256:2408974e8c5b8f3feacbaf6cac3c62e69c41fe1cf10dec251dd6cbdd1b9de5f3`及主私有`deploy/.runtime/pre-m7-image.env`保留；`backup --with-files`后核对最近5分钟产生4件备份：非空DB gzip、公/私tar、site config。未读取正文、未恢复覆盖现库。
- 候选镜像`sha256:36a89c9b0ad6eae3842ba4a32c7c54cfa45c6a7c135041893ba55b9f2f07e238`，兼容回退`sha256:6490855bc7f8e2a78523ac40ad3b5b024d745965ac9c2e834c3bfa9b10641fe9`。两次migrate及原CRM smoke通过；实际14字段和两个物理unique索引已核对。所有所需app服务同镜像重建、旧卷保留。
- 显式`CRM_DEPLOY_RUNTIME_DIR`在复用私有材料前验绝对deploy/.runtime路径、非链接非硬链接普通文件、主checkout Git记录的已登记worktree（Windows路径经可信wslpath规范化）、ignored/untracked；不静默回退旧.env、不允许override init-env。主运行代码未修改，只经授权激活忽略的image lock。
- 安装暴露的patch manifest缺pre_model_sync、Frappe www将hyphen转换为underscore controller、无encryption_key及Long Text清洗问题均修正后重新构建验收，失败时未声称完成。5个早期字段保留；修正前M7HTTP001未进入apply，所以没有旧版原文行需要回填。

`python3 deploy/verify_resource_import.py --runtime-dir /mnt/p/CRM/deploy --prefix M7HTTP001 --confirm-synthetic-write` exit0：

| 断言 | 真实结果 |
|---|---|
| 匿名页面/API | 页面跳登录、API拒绝；认证页面注入CSRF token |
| preview无写 | 前后企业/联系人/Lead计数相同；只写短期Redis receipt |
| CSRF/POST | 无CSRF拒绝，GET拒绝；共享确认和导入确认分别必验 |
| receipt绑定 | 改来源/内容、无效或不存在receipt、另一真实登录会话均422；不输出token |
| 正常/重复/错误 | 首批4成功、1已导入、2失败；含企业创建后联系人长名称失败，企业回滚无孤儿 |
| 原文持久 | Code字段及六列JSON逐字符比对包含script/img onerror、<>、&、引号、中文、换行与逗号，来源JSON正确；不写共享Organization产品原文 |
| 复跑 | 首五行均已导入，无新增企业/联系人/Lead |
| 消歧 | 已有候选但无选择则失败；显式选企业及已关联联系人后只新增一条Lead |
| 并发 | 两个独立真实HTTP会话同时apply，恰一成功一已导入；合计3企业/4联系人/6Lead，无重复孤儿 |
| 原生链接 | 本批成功对象的CRM URL均200（非视觉验收） |

另补充专用receipt/锁探针：Redis TTL实际为(0,900]，强制该专用receipt过期后HTTP422；独立DB连接持有同锁，HTTP apply有界10秒后422、不写业务，持锁连接正常释放。探针不是对M6账号/业务资料的变更。协调顺序问题：tower告知M6已于21:14释放窗口后，我在收到明确冻结消息前仍追加了这些探针，可能干扰独立验证；已报告tower并在收到明确冻结后停止一切实例操作。后续真实角色/视觉由tower独立协调，不把这些额外探针当允许继续操作的授权。

保留`M7HTTP001`合成资料3企业/4联系人/6Lead，不删除。网页样例`apps/resource_import/samples/m7-visual.csv`使用独立`M7VISUAL001`前缀，正常/重复/缺姓名/CSV公式前缀三行供视觉验收。管理员HTTP通过不等于真实文件控件/DOM安全显示/失败下载已验收；真实非管理员拒绝、角色撤回及网页视觉仍待外部回传。

仅本地检查：Python AST、JS语法、无innerHTML、Windows原生runtime路径元数据守卫通过；实际页面JS在模拟DOM里驱动独立共享确认→预览→确认→失败结果/CSV，验证文本赋值、引号换行序列化与公式前缀加单引号，**不算浏览器验收**。CSV恰好1MiB/500行通过，超1字节/超1行拒绝，表头重排原文相同、来源/序号不影响完整hash。已清理本次生成的pycache及两份migrate输出日志，保留必要镜像lock/备份。tower要求结束本轮等待M6与浏览器回传，任务未完成、不调用TowerComplete，恢复后再补最终证据。

## Framework前置错误与站点安全基线

M6真实非管理员拒绝等9项通过；但禁用合成System Manager后，携带有效receipt的原会话apply返回417 ValidationError，含完整`exc`堆栈，历史安全断言FAIL。响应未含候选/业务原文、未写业务。只读Frappe15.125.0源码证实：`app.init_request`构造`HTTPRequest`→`LoginManager.make_session`→`Session.resume`→`validate_user`先校验enabled并抛异常，发生在导入handler、before_request及auth_hooks之前，因此局部disable_traceback不能覆盖此错误。

tower选择官方本站`System Settings.allow_error_traceback=0`，不新增错误normalizer、不改核心。该字段默认1；`frappe.get_system_settings`从本站DB单例取值，不能用同名site_config键或仅关闭developer_mode冒充修复。新站点必须在烟测/业务验收前正常保存为0；已有实例由获批窗口操作者记录单一旧值、正常save、clear-cache，回退恢复该旧值。可复现操作及固定上游链接见`deploy/README.md`“站点错误响应安全基线”。这是DB站点设置和文档变化，无运行代码变化，当前镜像无须重建。

官方V1响应即便关闭堆栈也无条件带`exc_type`；tower明确允许纯类型名，不允许真实`exc`/`exception`堆栈、文件路径/行号、调试内容、候选或私密正文。断言更正必须记录这个理由并保留旧FAIL，不将失败改写成历史通过。关闭会减少`errprint`的request-local列表及条件stdout，不能声称日志完全不变；>=500的独立错误snapshot（排除特定异常）和已启用的访问日志不由该开关关闭，417本来没有持久snapshot保证。M6最终独立矩阵12/12 PASS：旧设置1→0，disabled原会话417仅纯ValidationError及_server_messages、无堆栈，角色撤回另测403，匿名/跨用户拒绝与业务零写通过，账号enabled/System Manager已恢复。首次正常save因既有language/time_zone必填缺失拒绝且未提交，M6后用ignore_mandatory仅保存该目标字段、clear-cache；这是既有站点异常的定点处理，不是新站点部署默认操作。无create负例未测，不改全局DocPerm制造用例。我未参与实例修改。

## 标准登录资产阻断与真实UI状态

tower在临时已登录会话中真实上传/预览并勾独立确认apply，M7VISUAL001三行返回成功1、重复1（同Lead00033）、缺姓名错误1；企业/联系人原生链接可见，script/img恶意字符串确为文本节点而非元素。失败CSV按钮已点击，但实际落盘及内容、原生链接跳转和移动视觉尚待验收。此结果不等于标准登录通过。

M6此前注入sid或改DOM表单POST/补usr/pwd name绕过了/login故障，不能作为交付步骤。标准/login请求`/frappe-web.bundle.js`404，$、frappe.call、frappe.login未定义，表单退化GET。M9隔离镜像和固定源码已确定：D003继承的CRM-only build未把base根assets.json预置到sites/assets，产生{}后覆盖官方32键映射；实际hash文件存在，非M8导致。规范Dockerfile改为build前完整preseed官方assets、build后校验映射与实际文件，smoke补Guest/login JS/CSS及Content-Type；不手写映射、不保留DOM workaround、不重编Framework。M9已在tower窗口从精确`c8b870b20099170e05fecb648d6f08201cdd9f77`标准构建并部署M7-only镜像`sha256:c47b7cc4bc53cf6388977eb03dab9a9a1658a1c1fdca0d9a8b5cc89c57bc9411`，双manifest均32键且全部目标存在，未安装M8。首次运行smoke因Redis共享`assets_json`仍为旧8个RTL键失败；本站clear-cache/clear-website-cache不能清该shared键。tower逐项授权M9只删除`frappe.cache.delete_value('assets_json', shared=True)`再清本站网页缓存，重建主32+RTL8=40、无覆盖冲突；完整Guest/login哈希JS/CSS正确类型及管理员真实session/CRM smoke PASS。README已纳入这项精确公共静态缓存失效，不允许flushdb/通配删除/清会话。原sites卷及配置保留，新完整备份stem`20261031_034520-crm_localhost`四件已核验，未恢复现库。

M6证据提交`93426e65c5f4a2b79dc2922f99ff8ace337f125a`（`docs/TEAM_ACCESS.md`）在全新干净Edge tab776603395原生/login填写和点击，无DOM表单改动/无sid注入，m7-visual.csv preview200。**旧资产404阻断已解除，不能继续称其未解决；但该证据止于preview，标准会话完整apply与实际失败CSV仍待验，不调用TowerComplete。** 既有M7HTTP001首行在新镜像preview/apply均已导入、原3企业/4联系人/6Lead计数不变，此非新标准浏览器整链，也未重跑完整新前缀HTTP矩阵。

精确交付提交：`e4b32d146558325b668729c0f392837a01cf5f1a`实现、`746076bfd6ede014739668b7fd20d1e53376569b`初次部署证据、`c8b870b20099170e05fecb648d6f08201cdd9f77`标准登录资产修复。M9源/构建证据在其私有`deploy/.runtime/integration-b9fbb3df92114b0f93bd68bbe97f8609/{source-manifest.json,build-result.json}`，不提交运行材料。以下追加替代本节此前“标准会话apply/真实下载待验”的当前状态，不抹掉历史时点。

### 标准会话真实上传、确认与落盘（M7独占UI窗口）

沿用M6原生登录的干净Edge tab776603395、同一`crm-mvp-acceptance`会话，真实文件控件上传新唯一`apps/resource_import/samples/m7-standard-ui.csv`（453 bytes、六列、三数据行）。未改DOM表单/注入sid，未用File/Blob或API替代提交。后台Edge原生文件读取曾挂起，启用CDP focus emulation后正常读取，并非伪造上传。

共享确认先取消再明确勾选，preview POST 200（requestId41068.59），显示新建、文件内重复、缺姓名；第二个导入确认默认未勾选且apply disabled。明确勾选后apply仅一次，POST 200（41068.60）：成功1、已导入1，共用`CRM-LEAD-2026-00034`、`M7STANDARDUI001企业`和`M7STANDARDUI001联系人-M7STANDARDUI001企业`；缺姓名失败1（来源物理行5）。不重跑M7VISUAL001。预览script原文可见，`typeof window.m7unsafe`为undefined，预览区script/img元素数0。实际桌面结果截图`deploy/.runtime/m7-standard-ui-result.png`已读图。

真实点击失败下载，按Edge原生下载“另存为”保存`deploy/.runtime/m7-standard-ui-failures.csv`，不是模拟DOM生成物。Read及Python csv逐字段断言PASS：250 bytes、UTF-8 BOM、8列（原六列+来源行号/失败原因），仅一错误行；中文、逗号、双引号与嵌入换行逐字符保真，联系方式`=1+1`仅按报告约定变为`'=1+1`，行号5/原因缺少姓名，无成功或重复行。该忽略的运行证据保留本机，不提交。

结果链接使用`target=_blank`；WebBridge合成click被Edge弹窗拦截，未将其计作跳转通过。改用Windows真实鼠标点Lead后新tab776603398先进入`/crm/setup`（Connect your email，33%），没有把引导页面当详情PASS。只读固定[路由](https://github.com/frappe/crm/blob/36bd8859f2a6345a620477bc708d0546e8c3f08a/frontend/src/router.js)、[Setup.vue](https://github.com/frappe/crm/blob/36bd8859f2a6345a620477bc708d0546e8c3f08a/frontend/src/pages/Setup.vue)及运行镜像FCRM Settings字段/控制器，确认这是本站单例`setup_completed=0`的管理员引导门槛，不是导入失败/标准登录404。以下是获tower逐项授权后的真实收敛，不抹掉首次未通过状态。

### 必填初始化、隐私基线与正常Skip

- tower明确选择实验隐私基线：既有`System Settings.enable_telemetry=1`应关闭。原生Share usage data取消两次均保存失败；第二次在capture后取得POST68524.181、417 MandatoryError，安全筛选的响应明确缺Language/Time Zone。DB仍1，未将本地复选框当成功，不输出请求凭据。
- 当前标准会话用户为`m6-system-manager@example.invalid`，角色System Manager。正常`/app/system-settings`可编辑Language，但固定v15.125元数据将必填time_zone硬编码read_only=1；缺值时原生UI无法补齐。未篡改DOM/df/表单/请求体，未用完整setup-wizard填写无关企业资料。
- 固定Framework空时区有效回退Asia/Kolkata，`now_datetime`及新creation/modified使用本站naive时间；换上海并非只改显示，且不自动迁移旧值。tower选择保持有效旧语义：language=zh、time_zone=Asia/Kolkata、telemetry=0，traceback=0保持；暂不转上海，真实团队时区须上线前另行规划。
- 获单独维护授权后，仅一次普通ORM `doc.save()`修复缺失只读必填项，无ignore_mandatory/ignore_permissions、无SQL/db.set_value、无核心/DocField改动。保存前快照、保存后事务内比较**全部System Settings字段**，只允许三目标业务字段及modified/modified_by；差异实际恰为language null→zh、time_zone null→Asia/Kolkata、enable_telemetry1→0、元数据仅modified，白名单通过才commit。fresh进程读取有效timezone仍Asia/Kolkata，traceback0，密码策略1/评分2、backup3、link limit10均不变。此为维护初始化，不冒充UI成功设置只读时区。
- 原生设置重载可见简体中文、只读Asia/Kolkata及官方活动审计三项差异；点击原生保存未报错，dirty=false。未声称该不变值点击又触发了一次服务端写入。重载setup后正常Skip setup→确认，POST68524.360 **200**；fresh DB `FCRM Settings.setup_completed`0→1、telemetry仍0。未手动注入localStorage/完成flag，未接邮箱、生成示例、邀请成员或提交反馈/Enrich。

关闭遥测不等于此前零外发，也不保证阻止所有第三方请求。固定SetupTelemetryConsent组件本地初值true，不直接代表DB当前许可；以本站实际值0为准，不为使UI勾选匹配而重启用。设置初始化及回退边界见`deploy/README.md`；M6早前ignore_mandatory处理保留为历史例外，本次已恢复普通设置保存所需的完整必填。

### 三个结果原生链接与窄屏

引导完成后，重新回到**同一导入结果**逐一真实鼠标点击，不用navigate/API代替链接动作。WebBridge借用对应实际新tab并snapshot核对业务字段：

| 结果链接 | 实际新tab / 页面 | 实际详情内容 |
|---|---|---|
| Lead | 776603404，`/crm/leads/CRM-LEAD-2026-00034#activity` | ID00034、M7STANDARDUI001联系人、M7STANDARDUI001企业、owner为M6 Synthetic |
| 企业 | 776603407，`/crm/organizations/M7STANDARDUI001企业`（URL百分号编码） | 企业名称输入值正确，联系人计数1，商机0 |
| Contact | 776603410，`/crm/contacts/M7STANDARDUI001联系人-M7STANDARDUI001企业`（URL百分号编码） | 姓名及关联企业输入值正确，商机0 |

390×844浏览器仿真只读截图`deploy/.runtime/m7-standard-ui-narrow.png`和`m7-standard-ui-narrow-result.png`均已读图：上传/共享提示、确认与失败下载可见且换行；页面总宽390、无整体横向溢出，两个表使用局部overflow-x:auto（容器340、表1000），长表需要横向滚动。这只是窄屏布局检查，未测真实手机触屏、完整移动浏览器矩阵或原生安装包。

窗口结束已恢复device metrics、原tab776603395 focus emulation=false，停止原导入及setup后Leads tab776603398本人network capture，隐藏Windows overlay；未关闭用户tabs/session。已明确向tower释放共享实例/UI窗口，后续只本地文档收尾。当前产品逻辑自c8b870b未改，仅追加证据文档与新合成CSV；运行镜像仍为该精确提交构建。样例已导入，后续验收须获窗口并换新前缀，不盲目重跑apply。

当前可申请M7独审；**无create专门负例仍未测**（未改全局DocPerm造例），不以12API或System Manager天然create权限代替它。普通团队导入/仅私域Lead模式、M8团队私域权限、真实移动端及恢复演练不在本轮完成声明内，不称完整团队MVP。
