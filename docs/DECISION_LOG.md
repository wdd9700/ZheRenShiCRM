# DECISION_LOG.md｜技术与产品决策链

> **过程文件，不是一次性总结。** Agent 在做出较大的临时决策后立刻记录，再沿临时决定推进；交付时必须回看全链。  
> 创建日期：2026-10-31  
> 当前状态：D-001团队方向、D-002基座暂选、D-003派生镜像修复均已留过程记录；**可登录CRM基座及合成Lead写读烟测通过，完整团队MVP未验收**。保留初始记录并在相应条目追加实测，不将早期未知状态当最终结论。

> **当前发布范围优先**：以 D-001 的 2026-11-05 用户决定为准，v1.0 仅 L0–L3、Windows 使用端与团队集中服务端，L3.5 不在 v1.0。D-007/D-008/D-009 保留为当时规划与选型记录，不恢复已被后续决定替代的范围或开工要求；D-009 的并行顺序仅是早期规划历史，不是当前 v1 开工授权。各条“待验/未完成”按记录时点理解，后续证据沿原决策追加保留。

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
| D-004 | 2026-10-31 | 受认证六列资源导入 | Provisional（管理员合成闭环已实测，待独审） | 最小Frappe app，原生实体、双确认、幂等与行级事务 | 独审/升级回归；普通团队私域另验 |
| D-005 | 2026-10-31 | Note/Task私域补强 | Provisional | 原生对象默认Private、显式Shared及多入口守卫 | 固定版本真实权限回归和独审 |
| D-006 | 2026-11-02 | 本地同版本合成来源独立恢复 | Provisional（原生恢复/内容/重启/导出已实测） | 新合成来源→独立副本，不覆盖现站 | M8兼容修复、双用户权限、持久入口及已有加密字段恢复 |
| D-007 | 2026-11-04 | 自主至 L3 与时间段级日程安排 | Validated（方向）；实现待验 | 本地日程、团队忙闲与合成 ICS 单向导入优先 | L1/L2 前置及 L3 出口实测；外部连接另授权 |
| D-008 | 2026-11-04 | L3 app 与同源 CRM 集成路线（M22 B） | Provisional（中置信）；契约/功能待验 | 独立 team_schedule app/DocType，复用认证 ORM；UTC + IANA 源时区 | 局部 ACL、实际依赖、时间段 UI 与双普通成员全链验收 |
| D-009 | 2026-11-04 | L3.5 CRM 与日程业务关联及开工顺序 | User Decision（已决定）；实现待验 | L3 约定功能实现完成且 L2 业务/权限验收无阻断后，测试 L3 与实现 L3.5 并行 | 双门槛证据、关联/写回权限及业务全链验收 |

### D-001｜团队为架构前提，跨端先复用 Web

- **日期/状态**：2026-10-31 / Validated（仅需求方向，不代表实现已验证）。
- **触发与目标**：用户最新明确要求面向团队、集中服务端与跨端客户端，优先低迁移成本；旧稿“先单用户后团队”不再是架构约束。
- **已核实事实**：tower 方向广播及 M1/M2 报告确认该更新；Electron 不覆盖 iOS/Android；本机没有可验证 macOS/iOS 原生构建签名的环境。
- **候选与取舍**：一套响应式 Web/PWA + 集中服务端（复用基座，先选）；Electron/Tauri 桌面薄壳与 Capacitor 移动薄壳（确有原生需求后评估）；四套独立原生端（当前成本高，暂缓）。
- **决定/置信度**：团队身份、私域/共享权限是第一阶段验收门槛；Web/PWA 为暂定低成本客户端路径。方向高置信，四端体验与薄封装可行性中低置信、未验证。
- **边界/回退**：不承诺四端安装包；单用户只作最小烟测，不替代双账号 UI/API 越权验证。客户端不嵌共享管理员令牌；真实私域数据未授权不得进入演示。
- **证据与下一步**：M1 官方能力调查、M2 本机工具调查；后续验证桌面/移动 Web、团队账号、拥有者/经理规则和私域隔离。
- **复评/用户决策**：普通可逆选型无需用户拍板；真实资料共享、公网开放、付费原生分发等授权另行确认。
- **2026-11-05，v1.0发布范围（用户决定，替代早期跨端同步交付预期）**：本次仅交付L0–L3、Windows使用端与团队集中服务端；L3.5和其他平台不在v1.0发布范围。保留Web/PWA可演进架构，但不把其他平台、薄壳或L3.5作为本次验收前置。既有D-001团队身份/私域权限门、D-002至D-006数据保护和可回退边界不被缩小。用户选择先收口现有可用产品而非继续扩张验证；停止重复已绿未变模块、另造验证框架或临时保活系统。当前执行精确1c58626标准候选镜像构建、相关原生/四suite回归及最终产物原a8 SFC一次；一次Windows真实UI和远端部署由主控协调。本次源码完整SFC已通过，不等于最终镜像/UI或可靠托管通过。服务重启已有数据持久化证据，但WSL/daemon生命周期与前端依赖启动顺序仍须明确区分；先交已有证据和最小修复建议，不通过续租临时hold伪装服务可靠性。该范围是高置信用户决定，只有用户扩大版本目标时复评；当前无需新用户价值取舍。

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

- **资产修复已部署与精确共享缓存失效**：M9标准构建精确`c8b870b20099170e05fecb648d6f08201cdd9f77`→`sha256:c47b7cc4bc53cf6388977eb03dab9a9a1658a1c1fdca0d9a8b5cc89c57bc9411`，隔离probe双manifest32键/全部目标存在；在tower窗口统一部署、旧锁/镜像/站点卷及配置保留。首次运行smoke仍失败，因get_assets_json使用shared=True缓存，旧共享assets_json仅8个RTL键，本站clear-cache/clear-website-cache不能失效。tower逐项授权只`frappe.cache.delete_value("assets_json", shared=True)`再清本站网页缓存，新请求主32+RTL8=40、无覆盖冲突，完整Guest/login哈希JS/CSS正确类型及真实管理员session/CRM smoke PASS。此精确共享静态键失效已纳README必需升级步骤，禁止泛化为flushdb/清会话/通配删除。M6 `93426e65c5f4a2b79dc2922f99ff8ace337f125a`在新干净Edge tab原生/login无DOM修改/无sid注入并preview200，旧资产404阻断解除；该时点标准会话apply及实际失败CSV仍待，不能将preview与早前临时会话apply拼为整链；后续同一标准会话的新CSV整链真实证据已在D-004追加。

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
- **标准会话UI追加（替代上段当前blocked状态，保留历史）**：精确c8b870b已由M9构建/部署为c47b7cc镜像，精确shared assets_json失效及M6新干净tab原生登录已通过。M7沿用同一标准会话，真实上传独立m7-standard-ui.csv，明确共享确认→preview200→第二独立确认→apply200仅一次，M7STANDARDUI001成功1/重复1同Lead00034/缺姓名1；危险script显示为文本且未执行。真实浏览器失败报告另存为后Read及csv.reader逐字段PASS：UTF-8 BOM、8列、仅1错误行、中文引号逗号换行保真、公式前加单引号；非模拟DOM代替。原生Lead链接真实鼠标实点进入站点/crm/setup，非详情通过，后续依tower正常引导授权验收，不注入完成flag。
- **正常初始化与隐私基线即时取舍及实证**：只读固定CRM路由/Setup.vue/控制器和本站单项，FCRM Settings.setup_completed=0为全站管理员引导；tower授权原生Skip setup及确认（不接邮箱/生成示例/邀请、不改国家货币）。tower另明确实验隐私基线，将既有System Settings.enable_telemetry从1改0；不声称此前零外发或该项阻止一切第三方请求。原生取消实际POST417 MandatoryError（缺Language/Time Zone），DB仍1/空/空，失败保留。固定Framework空时区回退Asia/Kolkata，now_datetime和新creation/modified用本站naive时间，改上海不只是显示且不迁移旧值。tower选择B：language=zh/time_zone=Asia/Kolkata，保持旧有效语义，不混合合成历史时区；真实团队上线前另行规划。正常System Settings UI的必填time_zone固定read_only，未改DOM/df绕过；经单独授权一次维护身份普通ORM save、无ignore_mandatory/ignore_permissions/SQL/db.set_value，事务内比对全部字段仅三目标业务值和modified变化，白名单通过才commit。fresh读取三值zh/Kolkata/0、traceback仍0、密码策略/评分/备份等不变；原生设置重载和不变值Save未报错。重载setup后原生Skip→确认POST200，单项setup_completed0→1，telemetry仍0。此是透明的维护初始化加正常UI引导，不冒充UI设置只读时区。
- **最终M7视觉收敛**：同一标准登录会话、同一新CSV结果，经正常引导后逐一真实鼠标点击Lead/企业/Contact结果链接，新tab分别776603404/407/410；snapshot实见Lead00034、姓名与企业字段、企业联系人1，不以页面壳或200替代详情。390×844仿真两截图已读，页面宽390无整体横溢，长表局部横滚；非手机实机或原生包验收。已恢复metrics/focus仿真、停本人capture且释放窗口，不关用户tabs/session。实现代码自c8b870b不变，当前只补文档与独立样例，申请独审；无create专门负例仍未测，不改全局DocPerm造例。D-004仅管理员合成导入闭环已有真实证据，不标完整团队MVP/移动安装包/M8权限/恢复Validated。
- **复评/用户决策**：普通可逆app与字段暂定无需用户审批；真实数据授权、公网暴露或破坏性操作另行决定。后续按HTTP/并发/双账号与视觉证据更新。

### D-005｜原生Note/Task私域权限补强（M8）

- **日期/状态**：2026-10-31 / Provisional，实施前记录；未通过仍阻断完整团队MVP。
- **触发/证据**：M6真实HTTP证实私密FCRM Note detail及PUT越权均200，未共享Note正文经activities泄露。M8固定源码核对：permission hook False后仍有DocShare OR，query hook后亦share OR；get_docinfo顶层响应、activity counts和mentions存在旁路。单permission hook不足。
- **候选**：A 在原生Note/Task新增默认Private、显式Shared可见性，覆盖多入口官方扩展（暂选，保留原生UI/历史）；B 独立私域对象（损失原生UI，须迁移，暂缓）；C 单permission hook（已被源码证伪）。不接受脆弱全局SQL补丁。
- **决定/边界**：Shared只有可读父Lead/Deal者可读；写仍按拥有者/明确授权协作者，不能把父可读等同任意写。任务assignee是明确协作但仍须父可读。Comment定义正式共享业务沟通，UI须提示；私文使用Private Note。不自动发布旧Note/Task，不改正文，不向外发数据。
- **置信度/验证**：中低；需双账号直接接口、列表、CSV、活动、通知、共享撤回及UI实测和独审。M7仍仅管理员共享商业对象确认，不因此扩权。
- **回退/风险**：不得关闭安全hook重新暴露已经存入的私文；保留安全包、关闭访问或恢复隔离副本。不删权限字段，不把部署成功等同权限完整解决。
- **复评/用户决策**：这是可逆安全修复暂选，不需等待用户审批；真实资料授权/数据迁移/删除或业务共享规则改变仍须用户决定。各旁路未全部实测通过前保持MVP阻断。

### D-006｜本地同版本合成来源的独立恢复验证（M9）

- **日期/状态**：2026-11-02 / Provisional。沿用恢复文档 D006；主分支现有编号仅 D-001 至 D-005，实施前核对无冲突。
- **触发/已知事实**：候选四 app 镜像已 build/probe，通过不等于恢复。原 WSL 站点仅 M7；远端当前备份早于扩展安装，且远端仅约2GB、由另一 worker 独占，不可用旧备份冒充四 app 来源。
- **选择/理由**：在第一 Ubuntu 新建独立合成来源，再用原生四件备份恢复至另一独立项目/站点/数据库/sites/Redis/internal 网络/回环端口。拒绝覆盖原站点；暂缓远端取数（需协调且现有备份不适用）；纯替身/压缩完整性不能证明恢复。来源显式整数合成声明与操作员 ACK 双门，禁发信/调度/外发真实资料，保留所有源和副本。
- **资源/置信度**：本机可用内存约53GiB、Docker盘余约808GiB；分阶段执行、无 worker/scheduler，不在2GB远端加栈。原生恢复机制已有实证，完整团队验收仍中低置信；不依赖或冒称 M8 完整权限矩阵通过。
- **实测追加**：固定候选cae67cc（access0e5fed7/resource faa5f03）新来源四app安装及双migrate、原生备份20261102_202855→新项目restore均exit0。0400密钥和单库授权通过，12类完整记录/子表、103引用缺0、公私2文件、配置及源/副本受控JSON/CSV一致；两个新项目各6服务重启后基线完整不变，副本管理员HTTP新增唯一Note后再重启亦完整保留（Note4/105引用），来源未混入该记录。不是远端现站恢复，来源无加密key，已有加密字段解密仍未验。
- **失败与临时措施**：旧候选双SalesUser登录通过，读取受保护Note500，确证M8调用固定Frappe不支持的raise_exception参数。历史“owner合法GET500”称呼已纠正：最初Admin ORM传owner=A实际落为Administrator，不能算owner正向，未改旧owner凑例。Docker29仅internal网络忽略ports声明；经tower授权，仅本轮有界loopback relay（16连接/60秒空闲/3小时）完成HTTP，未改internal/daemon/firewall或添加外网；永久入口尚未修复。有界WSL会话亦非正式托管。此前两次新来源初始化失败现场及partial目录保留，确认新库不存在后才原生重试，不覆盖旧资料。
- **兼容补丁后续实测**：M8精确9c0c8f50e159fd58dc1a647b1884656377ef8a04仅API兼容增量clean/hold后，tower授权新context/build/probe及两个本轮项目备份后切换。deploy5b218c4/resource faa5f03，53源manifest cb5be231；新index34fc2237、amd64manifest22c02958、configfb00dd79，完整摘要与24层见恢复文档。两次四件备份完整可读后仅Compose替换三无状态app，DB/RedisID/卷/site及common配置/主镜像锁不变，旧镜像/context/备份/失败初始化现场全留。普通Sales A/B亲自创建Lead/Note且实际owner==本人，GET/本人PUT200、对方Private/PUT403、Shared读200写403、协作者写200再撤权旧/新会话403、私附件本人字节200/对方403均通过；两个项目6服务重启后完整12类状态与紧邻基线全等、旧/新会话同矩阵通过。不是M8整体独审或合并许可，不解除完整权限blocker。
- **离线交付/剩余边界**：按M13七字段/有序24层契约和tower独立导出授权生成新tar/release，真实tarSHA e00a4c2c6573588abec8d28ff8b33dab0f9d7ef5dcffe1250ee1c18b1601ebba，完整blob/index→manifest→config/逐解压层全等PASS；尚未传远端，不执行有维护缺陷的38cbcd0更新器，等修复独审及新窗口。仍缺M8历史/列表/搜索/用户导出/socket/UI等全矩阵、已有加密字段恢复和持久入口；本次不重做旧恢复，不把基础正常功能复验冒称完整安全通过。
- **可逆/复评**：新命名资源独立、失败保留，不删旧卷/记录/备份，不 down-v/prune/uninstall。恢复差异、缺引用、连接指向原源或资源不足立即停该步骤并报告，继续可独立验证事项。实际结果归档于 `RECOVERY_VALIDATION.md`，只证明本轮新建合成来源恢复，不证明远端现站或真实客户资料恢复。
- **用户决策**：当前无需另设决策卡点；用户已授权夜间本地隔离演练及不删数据边界，tower已确认源方案。扩大远端操作或真实资料范围仍另行协调。
- **2026-11-03，M19构建接入暂定（实施前）**：本轮只改deploy接入/离线验证，不build或改运行实例。M8精确6b70971f0ac12b2e96b959a61a4c8346eb0868e1两段兼容有限clean/hold；M19冻结1c66c7fe7274655388ffb0a709ed4ef18f85cfad仍待独审，不是最终构建授权。暂选专用Dockerfile.frontend保留c3873固定Framework基底、既有bench get-app完整依赖准备，全部pip安装先于补丁，随后严格check→apply→原preseed/标准资产构建→after SHA复核；旧入口保持不变。备选继承或复制fb00完整镜像树能固定实物依赖，但新增镜像供应链/Framework资产与可重复输入契约，未经审查不执行；M17仅39件证据不能当完整依赖。既有fb00日志的依赖层是cache命中，不能证明干净重建必然再现manifest before SHA，当前为中低置信假设；不匹配即停，不刷新baseline、不再安装包凑绿。精确Git commit导出白名单和逐文件SHA可离线核验；后续需M19最终审定tip、接入独审与tower新build窗口，才验证真实Linux依赖check/标准Vitest/build/probe/UI。无新增必须由用户决定的卡点；若实际不匹配，再记录镜像输入替代方案与复现条件并先审，不静默换设计。
- **M19接入离线结果追加**：旧1c66首审auto promise消费者回归后，收到新冻结1f48ddae07a09c8f0c09aaae6b9a55779dcfdab1（仍待重审，不build）。新集合15件，apply接口与before SHA未改，仅resources.js after变化。对精确Git blob做15组离线检查全PASS，既有Node受控测试18项、既有Python重放/拒绝及新after核验PASS；旧入口context兼容、manifest receipt/源码漂移与部分/额外文件拒绝、仅mock Docker命令/label负例均PASS。只是源码/受控验证，实际Linux依赖重建、标准Vitest/build/probe及真实UI尚未执行；不把受控回归等同M19独审通过。

- **M19已审构建/测试追加**：tower确认M19精确1f48ddae已clean/merge、主7962e5d，接入58a0fd68有限clean/hold后另授权一次第一Ubuntu构建/独立none probe；不rebase、不更新现有站点/远端。四源和原69件context/receipt f527b52d不变，标准Dockerfile.frontend一次build exit0，真实before7/check→apply→after7/guard5及标准CRM/team_access资产与原preseed强断言PASS；本机完整依赖源层cache命中，不声称全新机器字节级复现。新index f43a277d62eab434ba90922f36b8a75e86a99a7d0dbdede1cbb70bbe57783a6d/platform48b33d5065440e2800cc3f2812676d3071a61b62f4d093f0b5506c508f8440ca/config50836b19cb4ac574f53840c100123f87f19032c22788cbd63b12f2146537a69d与四label固定。辅助公开blob本机路径不存在的失败保留，标准docker save只读流核29blobSHA/引用链/原始config及28有序RootFS与inspect全等PASS，不落tar/不load。新none探针1b20b68d exited0及两个新命名卷保留；原四app/双32键全部目标/Node/CLI/33件team_access源SHA/after与guard PASS，完整Linux原生Vitest34文件326测试PASS，另实际bridge1测试PASS（受控18项包装，非真实UI）。48个已有容器所选ID/image/status/StartedAt/挂载与主锁最终完全不变。没有补装依赖/改变baseline/更新站点/远端传输/删资源；仍待另开更新窗口与M18新资产真实UI、M8全矩阵、已有加密字段恢复及持久入口，不标M9或团队MVP完成。详细命令/失败/警告/报告在RECOVERY_VALIDATION.md。当前无需新增用户决策；扩大站点或远端操作仍需明确窗口。

- **M19本地更新后续窗口（部分完成）**：tower另授权两个本地合成站逐站先备份更新，deployment仍58a0fd68。source四件新backup20261102_235948全读/config等后，仅原三app定点换f43a277d，更新前后12类原文/141引用缺0完整全等，DB/RedisID/image/mount/sitecommon字节/主锁及其他容器不变；仅明确assets_json与本站网页cache失效。普通Sales基础HTTP矩阵PASS，列表脚本三次因未证前提停站并保留失败：Comment额外未审端点403；B共享父Lead不在默认列表；将B仅本人集合对称套A遗漏原Admin旧Lead明确lead_owner/ToDo/DocShare授权。每次停source三app、退役relay，不改权限凑绿，recovery仍未更新、本候选restart尚未做。经tower逐步批准backend-only READ ONLY对照，A原生/compat/get_list为00002+00001、B为00003，逐ID都有明确授权且A未授权BLead不见；内部维护不是SalesHTTP。共享A对B可直读但默认列表不可发现为已证原生产品缺陷，TowerFinding另报、不升级共享可用结论或M8/M9完成。统一续验脚本/前提矩阵待独立复核，不再猜集合盲重试；source停写、旧recovery relay到期。详细事实/失败/证据见RECOVERY_VALIDATION.md。暂选按真实原生集合+独立授权双门核兼容，不热修产品或改分配；置信度仅源码/内部对照高，完整普通HTTP/重启/UI仍未通过。当前无需新用户价值取舍；扩大远端/真实资料或解决共享产品规则仍应协调，不能从局部成功推定已授权。

- **2026-11-03，source最小重启续验与宿主边界**：e3565f6绑定的原12d3 helper一次执行，重启前A/B核心合同通过，但六服务restart后line137完整Mounts数组直接比较失败；raw before未落盘，具体差异不可追溯，不称已证顺序。新94b517 helper/全字段比较a7282396独审clean/hold、215离线项PASS后另获一次授权，精确tip/7pins/原容器/挂载前检通过，仅原infra健康后原三appstart。单次37.799秒exit0：六原ID/image/完整Mounts不变，前次Before→ResumeBefore→ResumeAfter完整12类/143refs缺0全等、私JSON+12CSV全字段读回、本窗口restart前创建的旧A/B及fresh密码会话必要读取/严格403/列表原生授权集合/保存standard不变均PASS；不重做grant/revoke、standard创建或成功业务PUT，不冒称验证前次丢失Cookie。共享Lead不可发现、真实UI、第二站、M8/M9整体门仍开放。
- **宿主风险与当前临时选择**：额外只读收尾发现其他12旧/M7容器StartedAt/FinishedAt变化，先保留完整报告并实测仅停source三app，不重跑业务。限定日志及自有调用审计证实：preflight WSL调用19:13:45.500Z→dockerd PID350恢复；hold WSL调用19:14:25.818Z→PID342于19:14:28.885042启动/28.954758 Restoring containers→旧容器约19:14:34启动；全部早于source start脚本调用19:14:46.192和helper19:16:08.996。18对变化的ID/image/完整Mounts规范化均相等，其中6对纯外层顺序，12对生命周期真实不同；受影响容器现unless-stopped、source/recovery=no、live-restore=false。支持宿主daemon初始化自动恢复副作用而非source restart越界，但daemon退出/重新初始化actor、WSL idle或外部触发仍未知，其他DB/site内容未读故不证数据等同。不能靠停source保证全局零生命周期，也不为消除现象擅改宿主restart policy或停止其他实例。
- **复评/交接**：tower接受时间线后另授权只start原source三app一次供UI，9.001秒exit0，原infra保持健康；WSL及Windows回环Host crm.localhost ping200/pong、backend/websocket TCP及短窗口全部其他容器/daemon生命周期无变化。保留既有有界hold至2026-11-03 06:14:39+08、relay约06:15:28+08，按06:14前交接M18，不自动延期，不当长期托管；完整证据/失败/未知均记RECOVERY_VALIDATION。M18已恢复并核Guest表单；旧A/B秘密方案撤回，未读/改其密码。另获授权后标准维护ORM新建两唯一m18-ui-c011000普通Sales账号及强随机独立口令，welcome0、站点邮件静音、EmailQueue0→0，无manager/ignore权限/业务或share更改；只新建一个保护ACL私目录及继承文件，不改父ACL。当前用户/SYSTEM/Administrators三主体、非reparse、gitignored均核，父DeleteChild/generic及管理员访问边界保留。专用JSON只交路径供明确授权Read和表单fill，拒绝不shell绕过，绝不发密码正文；账号准备不当UI验收。当前无新增必须由用户决定的价值取舍；维持可逆source短窗口，不扩大宿主/真实数据/远端范围，永久托管和宿主生命周期控制仍须独立设计、授权与验证。

- **2026-11-05，标准四app→五app升级演练路径（Provisional）**：当前远端fb00四app缺team_schedule，需验证真实新备份→仅安装缺app→一次标准migrate/schema/readiness，不能把镜像包含app或旧离线tar通过当站点升级。原M13入口固定trial项目/站点/四卷/8088，现有recovery拓扑不能直接接入。候选为改产品project/queue guard（扩大已审工具边界，拒绝）、切daemon store/写shim（违背授权，拒绝）、在第一Ubuntu标准trial新四卷从既有合成bundle原生restore再升级（tower明确授权，采用）；原source/recovery/第二Ubuntu/远端数据保留。59bf旧classic门真实失败后交M13修复，不私改；977cfe2双store获clean/merge才执行。2c tar及135有序解压层全链已实证，复用同一字节不重build/save。r1在资源创建前因原M7前端8088占用停止；tower11:45:43Z明确授权仅精确M7 frontend临停并finally同ID/image/port/mount恢复，r2真实check/四app restore及非空公私2文件核对成功、收尾原M7恢复与旧资源守卫成功。随后自有快照finally未保护db绑定掩盖首异常；同现场唯一只读诊断确认cwd导致Frappe logger误指/home/frappe/logs/database.log，采用既有标准先chdir sites和受保护cleanup，不建假logs目录/改产品。置信度：隔离与原生恢复实证高，完整升级当时仍未过；按授权同trial接未完双迁移及原977升级，不重restore/新卷。失败保维护现场、原备份/镜像/锁和全部资源，不卸载app/删表或用旧四app服务回退。事实、报告SHA及最终状态见RECOVERY_VALIDATION首节；当前无新增用户价值取舍，真实资料、公网和远端部署仍需独立门。

- **同现场接续实证与剩余门（2026-11-05）**：自有cwd修正后真实四app快照、原977双migrate/clear-cache通过，12类103引用缺0/用户/公私2文件保持，System Settings摘要迁移后变化单列。原977升级同tar全链通过但pre-backup candidate_apps missing报FileNotFoundError，尚未新备份/install/schema/readiness；同路径问题已交M13，owner冻结22d94b0待独审，不由M9热改。原M7同ID/image/port/fullMount/policy/running恢复实证保持；r4自有finalguard包含restart_count不变量且报红，但丢失computed值，不能归因已证count误报。唯一另授只读r5保存当前完整contract无差异、count1/原109卷全metadata等值（共114，trial4命名+原trial cache匿名1），但不能追溯r4当刻差异；r5预设必须count差异的断言也红，全部保留，不循环探针或重restore凑绿。当前置信度只覆盖恢复/标准双迁移及现资源contract，完整升级仍未过；等精确工具独审与tower新恢复指令。tower后续明确下一自有guard先落完整computed/diff，仅获授权精确前端started/finished/pid/restart_count单列生命周期、最终running/无OOM/无持续重启；身份/image/Config.Image/ports/fullMount/policy和其他旧容器保护不放宽，不追溯改旧红，本轮未执行新guard。无需用户重新作业务取舍，持久入口与真实资料门不变。

- **22d94已审同现场升级后续（2026-11-05）**：tower明确恢复后仅导出精确已审工具，保原trial/runtime/真实migrated-twice与同tar，不重restore/双迁移/build/save。原工具真实越过cwd查询门，停写并生成20261105_174924新四件可读backup、load精确2c/configurator成功，只缺team_schedule安装进入after_install后在v1_constraints.py19 add_unique报1146 Team Schedule Member表不存在。原工具保留maintenance install-team_schedule-failed/stopstopped/lockrestored/metadataquarantined，未进入后续migrate/schema/readiness/after业务快照，partial schema不冒称全回滚。首异常已交产品owner/tower/high finding，选择保现场等最小修复独审及同现场resume裁定；拒绝手工建表/跳约束/重restore或旧四app回退。新先落now/diff守卫本轮真实通过，M7完整contract/running/noOOM/无持续重启finally恢复，其他旧容器/114原卷/daemon/mainlock全等；不追溯改绿r4/r5。完整报告9696564063d54c9d927f78fed96e2f1f939697b6424024dd14d24f75ea91803a与log164b5654a768024e7d465483a6fec9c7e61361abebc07bdd7c6740c64ea17e53见RECOVERY_VALIDATION首节。隔离/备份与失败维护机制实证高，完整升级仍未通过；技术缺陷不新增用户价值取舍，真实资料/远端/可靠托管门不变。

- **M32初装修复新候选与独立fresh门（2026-11-05）**：M32精确a07f5e7独审clean/merge后，tower授权沿2c只加入before_install模块映射刷新、install.py及对应测试，其他源码/前端资产保持、不全量重建。标准build和完整源资产守卫已通过，新index24e36e99/config41a88ded；新tar SHA23b3fb65569912ce2bc82761af236d5ba34cf1781251cba6f5a60f0d906c1966、140有序层原M13逐blob/解压diff_id链已通过。备选直接在r6手工建表/先migrate修好再称fresh成功拒绝；采用第一Ubuntu全新独立无端口站与六卷，真实标准安装后、首次migrate/约束重试前只读断七表/metadata/DocShare/五完整索引，再suite及标准migrate2验证幂等。原r1Framework建站已完成但自有seed末次System Settings.save缺language/time_zone真实红，未装扩展/迁移，报告1d22afcf保留；不是日程修复失败。tower允许同一无业务站核onlyfrappe后普通ORM补en/UTC及既定设置、不ignore mandatory，不重build/save/newsite。此是可逆合成站初始化，无历史时区变换或新用户价值取舍；r6partial与新四件backup仍冻结。随后同站唯一续作223.603秒exit0，四扩展标准安装全部实际0；首次任何migrate/测试内constraint retry前只读七表/metadata/count0/DocShare0/五索引列序与Non_unique/title及description longtext全过，根因suite实际7tests OK，再标准migrate2全0/schema完整逐值不变，再7tests OK。最终报告755f7c2928b7d5a2f9902869b61e43de38c31f98b24254dc0961737bf2a28509，16操作/34守卫全绿，137原容器/120卷/daemon/mainlock/r6状态SHA保持，自有5容器最终全停；12历史生命周期变化及首轮CSS诊断保留。当前fresh标准初装合同置信度高，但r6仍未知partial、未新读其DB，不能外推旧站恢复/完整权限/UI/可靠托管。manifest状态明确fresh-install-passed-not-maintenance-resume-approved，原r1失败字节保留；跨候选维护续作仍等精确M13工具独审与tower明确指令，不宣发布或M9完成。

- **242161跨候选本地partial恢复实证（2026-11-05）**：tower明确M13精确242161c独审clean/merge并授权同r6现场→已fresh验证24e；只用原from-maintenance显式确认入口，不改工具/guard、不重build/save/restore/fresh测试或基线双migrate。先核原B完整非.env文件布局/SHA与冻结相等并保存原state/锁等副本，再必要原infra及兼容24e只读查得实际team_schedule已注册、七表与metadata全缺/DocShare0，拒绝预设未注册而forceinstall。原工具依真实missing空集合不重复安装，新四件backup201546全可读→一次标准migrate→精确五app/七表/五完整索引/无DocShare/longtext→readiness/check/versions真实通过。唯一383.522秒exit0，report60cbdb415332fa5046e907a367191e0c6e08d40266f8ec6325e6ed8ef334f0c7；12类103refs缺0/用户/公私2物理文件/mail全保持，Settings摘要变化明确单列。120原卷与其他容器/daemon/mainlock保持，M7精确finally恢复，原trial全停；原B context/proof/reviewed临时文件/原锁/markers不变，工具preC state/lock精确等原B/A，原失败不擦除。暂选原生维护恢复而非手建表/卸载/覆盖restore，隔离和本地恢复置信度高，未外推正式权限/Windows/服务开机自启；无新增用户价值取舍。随后tower要求最小精确24e标准up/stop差集，不重恢复矩阵；另一次只读旧/新备份留存补核在daemon active/PID前提即红、尚未创建probe/读取备份或启动任何服务，报告d527b19c19c36893c57cfd3ada65b1001a5cc9893d36d09ea89c811705623ffd，不能把此helper未等systemd就绪当已证服务可靠性失败或备份丢失。后继仅等待实际daemon就绪，不自行restart daemon，具体结果另加。

- **精确24e本地标准重启差集（2026-11-05）**：按tower后继要求先提交r7证据fd8e381，再同trial一次原242161标准up/stop，拒绝重复恢复矩阵或重启daemon。实际同PID360由activating九次自然到active后才操作；197.237秒exit0、reportd069d13084af7bf81138f37c96c81024cd498dedc68dfb537d6fd8368b61af1b。重启后五app/原七表五完整索引/无DocShare/longtext通过，12类103refs/用户/公私2files/mail/settings全等r7，原B/新C八件backup当前完整可读（不造升级前SHA比较）；真实backend/front pong和nginx转发Engine.IO polling open/close、WebSocket101/Accept/frame0/正常close通过，未登录/业务room/通知测试。8ops/18guards全绿、148容器120卷/C runtime原字节保持，trial最终全停、M7精确恢复，原r1前检红/12历史生命周期变化保留。最小正常stop/up与传输恢复现置信度高；服务器daemon enabled/开机自启、长期可靠性、非计划Redis单独断连恢复与Windows/正式权限仍未验证，任务4不勾整项。原备份及B证据不删，manifest绑定真实r7/r8且not-release-approved；此是已授权可逆本地验收，不新增用户价值取舍，后续远端/真实资料/正式上线范围仍由主控协调。

- **指定证据独审与原任务收敛（2026-11-05）**：精确a4361fa发布证据独审seq114为clean/hold、findings none（[报告](../../../comms/reviews/review-feat-security-integration-and-isolated-recove-integration-v1-delivery-eviden-r1.md)），明确T4正常stop/up/持久性/HTTP与传输socket/标准常驻运行说明已足，T5受控导出关联追踪和指定证据独审子门已足。M17精确86b9dfaef4521e506f143451c0cd738c84cc1883的[运维记录§15](REMOTE_EXECUTION_C010600.md#15-既有-daemon-开机自启收口2026-11-05)（跨分支按该commit读取）补Docker/containerd既有unit active保持、disabled→enabled且11容器不变，无重启/新服务；其seq113 clean/merge仅批准该证据增量。依原任务收敛T4/T5，替代上一条“任务4不勾整项”和此前证据待审口径，不再要求整机重启/长期压测或重复恢复；这些及Redis异常恢复/BFCache/已有加密字段解密只保留真实未验边界，不新设v1.0必做门。当前hold主要是T2正式权限责任及最终24e目标部署/Windows入口；M8原owner只做既有证据对账，非重试被拒安全审。选择复用已验材料而非重开窗口，置信度对已证子门高、对未测边界不外推；无新环境/测试/候选字节变更，也无新增用户价值取舍，M9不Complete/MVP/merge，clean/hold不等全分支批准。最新任务状态及链接见RECOVERY_VALIDATION首节及五任务表。

- **classic层深交付修复（2026-11-08，Provisional，制作前）**：远端24e原archive verifier通过、新四件backup20261108_013716可读后，load实际`max depth exceeded`，未install/migrate，原工具维护停栈/恢复旧锁与metadata；M17后续已安全恢复原四app，不由M9操作远端。离线原config证实140个实际diff_id、history201中140非empty，累计多轮派生层超出classic overlay2常见128层限额，本地containerd snapshotter能用不代表classic可load。选择精确24e只读source stage→标准`FROM scratch`/整树`COPY --from`并显式完整还原原运行Config，目标1–2层；拒绝继续叠patch、改daemon/清cache、无证明export/import或重装依赖/重建前端。tower已批准、M13确认原verifier无base/层数下限限制；全部新digest/release/tar身份，不冒充旧24e。制作后必须核完整Config、有效rootfs文件内容/类型/uidgid/mode/链接/硬链/xattr与时间、固定源码资产五app及必要schema运行，原archive verifier逐blob/有序解压diff_id保持不改；真实差异立即报告，不静默放宽。只第一Ubuntu、本地可逆新产物，旧失败/镜像/卷/材料保留，不重权限/恢复矩阵；对减少层深的机制置信度高，对COPY等值须实测。首helper在daemon未就绪前检退出且operations空，未build/save，旧红保留；后继只同调用有界等待自然active不start/restart。无需新增用户价值取舍，远端后继交付仍由主控与M13/M17协调。

- **低层交付结果与metadata复评（2026-11-08，受测范围Validated）**：唯一标准build/save产出2层新index e17300da434bd0c251adf618c86db26c718511fec6ab6bfe2a99e7fd91bebe41/configcaf102a5716f4be0fc16ac9590038867bbe34c8e5419ff9fa92753ed6f1bf6d9，全部原运行Config逐值等24e；固定源码/五app/36资产运行与原242161archive verifier全过。完整173022共同有效项内容/类型/uidgid/mode/symlink/xattr/857硬链群等，严格比较只剩旧显式根tarheader与3目录mtime而红，报告f90de7ab与diff7021bb7a保留；实际四目录stat根root:root/0755及其余uidgid/mode/type全部相等。tower明确目录mtime/header非功能阻塞，暂选记录可见metadata差异并接受语义等值，而不是重build凑时间或隐去严格红；semantic报告b9ba477c2ffc78fd9b726b43bd6f04f780c5c2b7bdaef45d3f7ddb9188b69495。随后56.908秒实际只原M32隔离infra3启动、新候选READ ONLY五app/七表五精确索引/无DocShare/longtext等旧终态、finally infra3全停，报告8ba1f56fb989cf81cc9f8f517609d5f3affdedb3830757e5372191b9d78e0c2d，3ops/8guards全绿，不重install/migrate/恢复/测试矩阵。新tar1530942464B/SHA6d67a6fd359b3fe69489e2e7e52bfbbedf7f9f289172d19751e2f732c7a0608b及新release/2layers/manifest冻结在RECOVERY_VALIDATION首节路径，manifest e0e3c37f4598c93e6b1a9eed8b5d5303d096bc840e866c0c103992503c62b648。语义继承置信度高，classic远端load和目标部署仍由M17新授权实测，不能外推已上线；新config须原跨候选入口不是同代resume。旧材料/失败/新退出probe均保留，无删除/daemon改变/远端/第二Ubuntu或后台，当前无需新增用户决定。

- **M9正常v1权限依赖收口与最终交审（2026-11-08）**：tower确认M8正常v1核心seq115 clean/merge已正式合master67b90ee37deefe0316fedc3bf89bccfa52049f3b；审定531生产与rebase后0f7adb4ca18d35102818426a760a0ee730d25e2e逐字相同。依据既有e26双Sales/Shared/撤回/附件/重启、87e76列表筛选link活动CSV及旧新会话拒写无副作用、当前531正常L2 UI和source/recovery定向HTTP及既有备份/安装双迁移/导入结果，T2正常v1责任满足；不把高级组合未覆盖当无限hold，也不把seq115说成全面安全认证。M9五任务可交最终独审，completed仅等待审查/合并门，不是已合并或正式发布；低层新e173/caf102交付字节不变。历史R8拒绝、全部旧红、v2/复杂历史附件/高级视图/全身份子行快照/双room/PWA离线未全面验证及旧库准入限制完整保留，禁止伪标真实库为synthetic_only=1。远端最终上线与Windows归各owner，不外推已完成。只协议和两文档收口，无新测试/环境/大日志复验；置信度对正常已证核心高，高级未验不作保证，当前无新增用户价值取舍。最新任务映射及[seq115报告链接](../../../comms/reviews/review-feat-team-private-activity-access-extension-b-access-v1-bounded-release-revi-r1.md)见RECOVERY_VALIDATION首节。
### D-007｜自主推进至 L3，以时间段日程而非日历视图验收

- **日期/状态**：2026-11-04 / Validated（用户方向与授权边界）；具体实现方案 Provisional，功能未验收。
- **触发与目标**：用户明确“你的迭代自主权一致延伸到完成L3”，并强调日历不等于更细粒度、需要时间段标注的日程安排。补充 D-001 的阶段范围，不撤销团队安全基线，也不重写 D-004 的旧时区事实。
- **已核实事实/未验证项**：本次依据用户最新明确要求更新三份既有文档，未访问运行环境。旧记录保留现站 `Asia/Kolkata` 历史语义；L1/L2 仍须修复与全流程验收，L3 本地日程、导入与第三方同步均不能据本文称已实现。
- **候选与取舍**：仅交付日期格子/待办期限（粒度不足，拒绝）；时间段日程 + 本地协作与合成 ICS 单向导入（先选，可独立验证）；立即连接私人账户或直接承诺双向同步（缺凭据/专项授权与真实证据，暂缓）。复用基座或最小扩展的可逆技术选型由 Agent 调查、记录后推进，不预先绑定新组件。
- **决定/置信度**：自主目标覆盖 L3；开始/结束、明确时区、分钟输入、日内多段与跨日、忙闲与冲突提示为核心。两名普通成员创建/修改/取消、共同空闲区间、私人仅忙闲及授权业务协作为出口，具体复现要求见交接文档 L3。用户方向高置信，具体实现与同步适配可行性未验证。
- **导入/同步默认**：先本地创建及合成 ICS 单向导入，预览确认、来源标识去重、更新/取消匹配、歧义报告、逐项失败与幂等重试；后续真实连接须明确方向与冲突/恢复行为，不将合成导入说成真实第三方同步完成。
- **安全/可逆性**：不因自主授权连接私人外部账号、外发邀请或自动改排/取消他人安排；冲突先提示。不迁移旧历史时区，不擅改现站 `Asia/Kolkata`，新增日程独立验证时区转换。普通可逆实现可自主推进，L4/L5 不在本轮承诺内；回退保留日程及来源数据，不用删除历史或撤掉权限保护作捷径。
- **证据与下一步**：本次为范围/验收文档增量，无功能实测；实施者须提供交接文档 L3 的双普通账号 UI/API、时区与持久化、共同空闲、私密旁路、ICS 重复/更新/取消及失败恢复证据。L3 可并行准备，不替代 L1/L2 前置验收。
- **复评/用户决策**：当前范围与普通可逆技术选择无新增必须用户拍板卡点。只有实际私人账户授权、外发邀请、历史时区迁移等敏感或不可逆边界需另行决定；缺授权不妨碍本地/合成验收，未来用户方向变化或基座能力证伪时记录新决策复评。

### D-008｜L3 暂选独立 team_schedule app 与同源 CRM 入口（M22 方案 B）

- **日期/状态**：2026-11-04 / Provisional；主控已暂选，在产品编码开始前记录，不代表契约或功能已验收。承接 D-007 的 L3 方向，L1/L2 安全与业务闭环前置仍有效。
- **触发与目标**：依据 M22 只读复用调查，以最小可回退实现承载具体时间段、团队忙闲与协作，避免把私事放入现有 Event/Task 的共享与同步路径，也不另造认证或孤立产品。
- **证据/未知**：M22 `survey-summary`（2026-11-03，消息 ID `f37cfddb-ef38-402d-89c3-21da7af643c0`）核对 Framework v15.125.0 及 CRM commit `36bd8859f2a6345a620477bc708d0546e8c3f08a` 的可得源码；报告指出 Event 终点可空、参与者路径会同步标题正文到 Communication，原生查询不是脱敏 Busy-Free 接口。部分 Event 证据来自公开固定 release tag，未逐字核对运行版本；依赖声明不等于实际安装/API可用，调查未执行功能测试。本条依据该报告与主控暂定决定，未访问运行环境。
- **候选与取舍**：A 原生 Event 加字段/控制器（可复用现成时间格，但需约束终点、Communication/提醒/同步及多入口权限，忙闲与详情授权未分离，回归面大，暂不直接承载私事）；B 独立 `team_schedule` Frappe app / 日程 DocType（暂选，可局部定义数据与权限边界，代价是新 UI/ACL/导入器，新类型并不自动安全）；C 外接 CalDAV/排程服务（增加认证、数据副本及同步恢复成本，当前无必要，暂缓）。
- **临时决定/置信度**：采用 B，复用原有标准会话/认证、CSRF、ORM、事务、迁移与备份基础；通过同源 CRM 导航统一入口并可返回 CRM，不以独立 www 页面代替普通成员正常 CRM 全链验收。中置信：可隔离、可替换，但局部 ACL 能否封闭所有旁路、依赖实际可用及时间段 UI 尚须验证。`docs/SCHEDULING_L3.md`（M23 待完成）仅作为实现契约候选，待审定，不声称已冻结或已验。
- **时间/权限边界**：新日程使用规范 UTC 实际时刻 + IANA 源时区，具体编码与控件转换由后续契约明确并测试，禁止二次转换或把旧 naive 历史当 UTC；不改既有 `Asia/Kolkata` 历史语义。服务端 Busy-Free 投影不含日程 ID、标题、正文、关联私密信息或来源 UID，仅含必要成员标识与占用时段；忙闲读取授权与详情/编辑授权分离，不靠浏览器删字段。冲突仅提示，不自动改排他人。
- **导入/依赖默认**：首版受限合成 ICS 单向导入，先预览再确认，明确支持子集、来源隔离去重、更新/取消及失败重试；不支持项明确拒绝/报告。优先核实现有 pytz/dateutil/vobject 的实际版本与 API，缺失时报告后再选最小固定依赖，不以依赖声明冒充可用。真实私人账号连接、双向同步及外发邀请另需实际凭据/明确授权并独立验收，不自动执行。
- **下一步验证/复评**：先做局部 ACL spike，覆盖标准详情/列表/搜索/导出、DocShare/子表等旁路及撤权，避免复制全局拦截；核对实际依赖，再验证分钟输入、跨日/时区、两名普通成员 CRUD、Busy-Free/共同空闲、授权协作、合成 ICS 与正常 CRM 导航。任一关键能力或局部权限无法收敛、集成成本失控时重新比较 A/B/C，记录替代决策；不得将新 DocType 或 M23 文档完成当功能验收。
- **可逆性/用户决策**：可先停新日程写入/导航，保留 app/schema、权限、日程及来源/取消记录，按授权导出带 UTC/源时区的中立数据；不卸载删历史、不关闭安全保护回退。本次为可逆技术暂选，无新增必须用户拍板卡点；私人账户、邀请、历史时区迁移等敏感边界仍另行决定，L4/L5 不在承诺内。

### D-009｜用户决定新增 L3.5：L3 实现与 L2 测试门槛后并行推进业务关联

- **日期/状态**：2026-11-04 / User Decision（用户已明确决定阶段名称、范围与顺序；不是 User Decision Needed）；实现/验收未完成。本条增补 D-007/D-008，不改写其历史事实或撤销 L1/L2 安全基线。
- **用户原话/证据**：“对的，那就叫L3.5，排在L3实现之后、L2测试没问题之后，测试L3和实现L3.5并行推进”。依据主控转达的最新明确决定及 M23 mission 同文交接记录；本次仅更新文档，未核验运行状态，不称 L2/L3 已完成。
- **目标与范围**：L3.5 是 CRM 与日程的业务关联层：企业/需求/商机/任务受控关联，活动目的（如需求澄清）与实际业务结果分离；业务/任务负责人按原权限读取原记录，区分日程牵头及参与分工；会后结果经人工确认与目标写权限校验后回业务时间线。关联不自动改派业务负责人，不因日程结束而认定任务完成或业务结果成立。
- **开工双门槛**：L3 约定功能实现完成且 L2 业务/权限验收无未解决阻断；局部后端完成不能替代 L3 约定功能实现完成。主控须依据相应实现与测试证据判定门槛，本文不是通过证据。满足后测试 L3 与实现 L3.5 并行，不要求先等 L3 全验收；未满足不得提前编码。
- **顺序取舍**：现在提前实现（违背双门槛，不选）；等 L3 全部测试通过再开工（比用户要求更晚，不选）；双门槛满足后并行（用户已决定，采用）。不是 Agent 技术偏好，也不将后续 L4 AI 当前置。
- **权限/非目标**：关联不授予权限，日程可读不推出业务可读/可写，原记录读取及会后写回各自校验授权并处理撤权；忙闲不泄露业务摘要，不复制敏感摘要绕过原权限。保留 L3 私域及忙闲/编辑分离，不引入完整项目管理或自动外联，不把 L4/L5 混入本阶段。
- **置信度/下一步**：用户意图与顺序高置信；实现方案尚待对应 owner 细化及验证。本轮只落路线/决策，不改其契约或产品。开工后用双普通成员验证受控关联、原记录读取、牵头分工、目的/结果分离、人工确认后时间线写回、撤权及忙闲不泄漏，并继续独立测试 L3；未测不得报交付。
- **可逆性/复评/用户决策**：保持原业务记录与历史，不用复制私密内容或删除历史作捷径；后续实现应允许停用关联/写回而保留已有权限与审计。门槛证据不足或实现/权限测试出现阻断时报告并修复，不以并行安排降低验收标准；范围或阶段顺序变化须记录新决定。当前无需重复索取本项决定，敏感授权仍按原规则另行确认。

### D-010｜哲人石CRM默认中性暗色与连续日程时间轴（M35）

- **日期/状态**：2026-11-08 / Provisional，实施前记录。
- **用户方向与目标**：产品展示名为“哲人石CRM”，默认暗色；玉青、蓝、金只用于高亮、细边和标识，不作大面积背景或正文。统一字号与间距；日程参考用户指定Class Widgets纵向时间轴和占用色块方向，不复制第三方源码/图片。
- **选择与取舍**：采用固定上游原生dark scheme加独立`frontend-patches/dark-ui`覆盖，以及同源`crm-theme.css`；拒绝改写M24安全补丁或整套替换前端。集成必须按M24生产43 entries→M30导航→dark-ui→独立汉化顺序；本分支旧c011000不是生产最终前端。
- **日程决定**：默认单日连续纵轴，所选IANA时区两次当地午夜由现有resolve_local解析；按真实UTC分钟定位、裁切跨日、重叠分列，短事件真实薄块配独立可读标签，不夸大占用时长。不新增拖拽/复杂重复规则，不改变API、权限、revision或会话清屏。
- **字典与边界**：Terra独占中文字典，显示文案与Busy/Free/Read/Edit等原始值分离。共享主题接入日程、私域活动和导入页面；Framework登录不在本次页面scope内，不宣全站汉化/上线。
- **置信度/验证追加**：受控源码与静态合同高、真实外观中；既有+新增Node33项、Python UI5项、dark-ui文件check/apply/after及拒绝4项、原access page.js验证均通过。精确e173/caf102镜像frappe-ui1.0.0-rc.2实际token生成器与底表证据已核，未猜变量。canonical与CRM payload同字节SHA，专用.gitattributes仅该CSS强制LF，避免Windows转换破坏契约。首轮新增分页测试因旧异步事件handler不返回promise而断言过早失败，补flush后通过，未改请求或放松断言。标准CRM构建和真实浏览器/三页外观验收由M37后续集成窗口负责；Framework登录与入口HTML/PWA品牌不外推完成。
- **回退/复评/用户决定**：仅可逆展示层与独立补丁，无后端、数据迁移或部署；可撤回主题和时间轴展示但不能撤安全补丁。高并发可读性、实际浏览器表现或上游SHA变化触发复评。当前无新增必须由用户决定的卡点。
- **M37集成暂定（owner交接，制作前）**：复用冻结两层e173/caf102精确源码，独立U030构建context保旧deploy路径不变；M37已核M24从1c586261到9403d5a生产补丁整目录无差异、M30从4ff到76f23be仅README差异。采用M24 43→M30→dark→localization→branding有序组合，最终逐target SHA承认有序重叠、不伪称全体disjoint；标准bench build沿既有资产preseed且不重装依赖，避免回到140层基底。登录展示由固定入口title/apple/lang（取boot.lang）及CRM原生update_website_context在Framework登录context后接线，限文案/CSS，不改认证、版权、包名或权限。中文System Settings.language=zh只在后续明确授权窗口配置，保用户/cookie/header和时区语义。此为M37源码合同交接、高置信于已核源码，标准build/真实UI仍待各冻结tip独审后实测，不是本次已执行或上线证据。

- **Sol首审seq118后定点修复**：两项P2为午夜`top=0`被`||`滚动fallback跳过、分页未全量提示被读取详情的status覆盖；改为空值fallback，另在结果容器内保留分页提示，不与详情状态共用。新提示随原清屏一并移除，末页自然撤下。仅补既有DOM回归（午夜/跨日scrollTop、详情后提示仍在、加载末页/会话失效清除），18项DOM测试全过，不扩后端矩阵或执行build/部署；待新tip复审。

- **d573视觉反馈后集中修复（2026-11-08）**：Terra `visual-8a9a3322-2c35-4ada-9607-31fd4eeb0da7` 于1280×720实测时间轴y647才开始，确认首屏信息密度不合预期；后续截图超时不当算法错误证据。采用实际DOM主轴前置、紧凑标题与日期/时区工具栏，说明筛选折叠在结果后、编辑区移后，轴视窗clamp(320px,100dvh−280px,680px)，不缩正文、不改ID/功能/清屏；代码合同先验，最终截图待集成；同步移除初始滚动的旧480px固定视窗cap，保首事件top−48并由浏览器按实际视窗裁限，午夜/末分钟目标有DOM回归。旧access注入白底链接未设color继承浅字、黄底编辑器提示均改中性前背景token/独立fallback，保Observer/通知/路由。默认紫标来源CRMLogo硬编码#EF0BF5，仅UserDropdown无brand.logo时改自有中性“哲”小标+3px三色点，明确自定义logo及原组件/版权/资源不删。GettingStartedBanner字面英文和theme=blue由实际固定源定位，M35只交rc2已核gray/subtle样式片段，M39同文本补丁合成、不并改文案。定向UI6项（内调Node35）、dark补丁5项与既有access page.js验证通过；首个布局合同用子串order误匹配border而红，已改CSS属性边界正则。M37须收新增access.js overlay及更新标记/同源CSS after SHA；本轮无环境/构建/浏览器操作，不据源码验证宣实际外观已过。

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
