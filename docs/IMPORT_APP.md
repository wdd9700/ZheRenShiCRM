# Resource Import：受认证六列网页导入

状态：M7设计在实施前记录（2026-10-31）；现已在tower协调窗口部署、管理员真实HTTP矩阵通过，非管理员实会话与网页视觉待验。对应 M5 实际源码 `tools/crm/m5_import.py` 与 `docs/MVP_WORKFLOW.md` 第6节；后者是建议，不是安全实现。

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
- preview POST不建File、不写业务库；只在现有Redis写15分钟随机不透明receipt（不保存CSV原文），绑定用户、session、来源、文件完整digest及共享确认；apply必须确认且receipt一次绑定同一会话/文件/选项，服务端重新解析、重新做权限/候选计划。receipt丢失/过期/篡改/跨会话/跨用户均fail closed并要求重新预览；不能把receipt替换成另一份内容。调用者身份 `.insert()`，不使用ignore_permissions/set_user。错误仅返回固定分类，不泄露异常正文、SQL或堆栈。

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

## 已执行证据（M7协调窗口）

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
