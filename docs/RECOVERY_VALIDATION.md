# 安全集成、隔离恢复与重启验收（M9 / D006）

状态：**M7-only 登录资产修复已构建、备份、统一部署并真实登录/导入幂等验证通过；本轮只读健康窗口已完成并释放。M8 精确候选 0e5fed78841f8acad31278a3e06cb08b0e6e93d0 的完整独审仍未完成；未安装 team_access、未恢复、未通过安全版重启或权限验收。** 修复复审 clean/hold 不是完整审查、合并或安装授权。初始组合 509df32 仅用于早期离线探针，不可作为最终安全版。当前未经 tower 新授权不执行共享 Docker、HTTP、数据库、Redis 读取或写入。备份存在不代表恢复成功。仅第一个 Ubuntu-24.04、合成资料；不触碰第二发行版。

## 本轮精确来源归档与恢复确认适配（未构建、未运行恢复）

- 2026-10-31 只读健康窗口：第一 Ubuntu Running、第二发行版 Stopped；主运行锁和7个应用服务仍一致使用 M7-only `sha256:c47b7cc4bc53cf6388977eb03dab9a9a1658a1c1fdca0d9a8b5cc89c57bc9411`，原 sites/DB/Redis 卷保留。主 checkout 的标准 status/smoke 与 Windows smoke 均通过，覆盖 Guest 登录映射资产/类型、ping、既有 Administrator 会话及 CRM 资产；没有新增业务记录或改账号。这不是最终安全版重启、业务图或权限持久化证明。原8小时保活进程当时仍存在，未重启、续期或终止；不能将应用退出或旧任务 lost 当成 OS 进程已经结束，也不能将短核验命令当正式保活。
- 仅本地归档并立即逐文件核验 context `deploy/.runtime/integration-837f2d1c345048559fdab4b05fe09c79`：部署来源 `781fba11f2588fa38503c9539b1db096366c9304`，resource_import 来源 `faa5f0330ad54bd9f4d02bb498ea305651c95ed9`，team_access 来源 `0e5fed78841f8acad31278a3e06cb08b0e6e93d0`；53文件（18+33+2），manifest SHA256 `7d1506ba87354547e09a36c4884e4159c66b6d204909a3cc05751a5b0d15c031`。无 candidate-image.env/build-result.json，未 build、未探针、未改主镜像锁。**本节恢复确认适配提交后，该 context 是过时来源证据：保留原件，禁止用于最终 build；新 tip 独审后仍须重新归档核验。** 精确 blob 导出不要求 M8 先 rebase，但不代替正式依赖整合和新 tip 审查。
- 本轮恢复适配只允许“双确认”：操作员在 `restore` 显式传 `--confirm-synthetic-only-data`，且备份源配置的 `team_access_synthetic_only` 必须严格为 Python/JSON 整数 `1`（拒绝 bool、字符串、浮点数、缺失或其他值）。CLI 不接受继承环境的确认；仅向 restore 服务传入本轮确认标记，Compose 渲染结果必须与之相同。`recovery_site.py` 在写 sites/common/site 配置和调用原生恢复前核验两条件，成功才将源整数值写到新副本；没有默认 `1`，不修改源配置或备份。**这是显式合成资料声明，不是资料真实性检测，也不许可引入真实资料。**
- 离线验证通过：纯内存源/操作员确认15反例、环境偷渡剥除、5种非 restore action 错用 flag 拒绝、restore 缺 flag 在 Compose 前拒绝、显式传递及直接 restore 调用缺确认拒绝；内存执行 site main 验证成功写整数1/隔离目标/维护模式，4种失败不发生任何写入，源保持不变。第一 Ubuntu 的真实本地 Compose config 分别渲染未确认/已确认状态，确认字段仅出现在 restore；6种确认字段缺失/相反/非法值的渲染变异均拒绝。全部署 Python AST 和 `git diff --check` 通过。一次 WSL 调用因 Git Bash 路径转换失败，设置 `MSYS_NO_PATHCONV=1` 后上述本地渲染通过；未连接 daemon。
- 仍未验证 Docker/MariaDB 初始化、0400 keys 实际读取、SHOW GRANTS、原生 restore、真实副本配置/HTTP/权限/业务图。未执行 build、容器或卷创建、receive/restore、install/migrate、删除或保活续期。后续 `--build` 使用 `docker build --network host`，get-app/pip 隔离构建可能访问 GitHub/PyPI；只有源码归档是离线，不能把构建声称为全离线。网络/7897代理及缓存完整性仍待独立授权核验。

## D006｜同版本、独立项目和卷的恢复演练

- 日期/状态：2026-10-31 / Provisional，实施前记录；待 M7 结束 D004/D005 日志独占后追加总决策链。
- 目标：证明数据库、公私文件、加密配置、原文和关联及团队权限能恢复，且恢复副本可真实登录读写。不覆盖现站点来证明备份可用。
- 已知事实：Framework 15.125.0 / CRM 1.90.0；原项目 crm-mvp-v15、站点 crm.localhost、入口 127.0.0.1:8088。resource_import 已安装，不能换成缺该模块的镜像。team_access 禁止直接卸载或停用权限 hook。
- 备选：仅检查备份 gzip/tar（不足以验收）；恢复覆盖原站点（风险大，拒绝）；同版本独立 Compose 项目、站点、数据库/sites/Redis 命名卷（暂选）；跨版本迁移（同时改变变量，暂缓）。
- 暂选：安全 app 集成与真实权限回归后，停写窗口产生新数据库及 public/private files、站点配置备份；核验完整性并保留原件。使用同一不可变安全镜像、相同 DB/Redis digest，在新项目 crm-recovery-b010200、站点 recovery.localhost 和独立命名卷恢复。入口仅 127.0.0.1:8089。新项目不挂原项目任何卷，不引用原 DB/Redis。恢复须保留原 encryption_key 等必要配置但不得打印正文/摘要；仅恢复副本可更改连接/站点路径适配。
- 置信度：方案中，执行低（尚未实际恢复）。Frappe 原生 bench backup/restore 可复用；同版本真实 restore 参数、文件路径和站点配置适配仍待在候选镜像中核对。
- 可逆性：原站点、原命名卷和所有旧备份均保留；停止副本即可退出演练。不使用 --rm、down -v、prune，不删记录/容器/卷/备份，不为重试覆盖既有恢复站点；失败保留现场另行协调。
- 安全回退：保留含 resource_import 和 team_access 的安全镜像及全部权限 hook；失败保持维护或停业务服务。不可回到缺 team_access 的旧镜像恢复对外服务。
- 复评触发：原文/关联/文件/权限任一不一致，无法真实登录读写，版本不一致，或副本误连源服务时立即停止验收。大于 team_access 2000 行上限应 fail closed，不能把空结果当成功。
- 用户决策：当前无新增必须交由用户决定的技术卡点；扩大网络暴露、真实资料引入、正式长期系统服务仍需另行授权。本演练不创建系统服务。

## 构建与迁移计划

候选允许用于提前验收，不代表绕过 M7/M8 最终独审和依赖合并门。M9 只提交 deploy 和本页，不复制 app 到自身分支，也不 merge 其他 mission。使用精确已提交 app 源码归档到本工作树忽略的 deploy/.runtime 下，记录来源 commit 与每文件 SHA256；不复制他人未提交文档。

初始候选（以完整 SHA 为准；可能随独审修正更新）：

| 组件 | 已提交来源 |
|---|---|
| resource_import | 746076bfd6ede014739668b7fd20d1e53376569b |
| team_access | 509df32e33abf477693503bc4c1a8052e476fe6a |
| CRM | 36bd8859f2a6345a620477bc708d0546e8c3f08a |
| Framework 基底 | ghcr.io/frappe/crm@sha256:c3873edce03a0e9327306092c5f392b182304d905f9286057f90fb5739f810ca |

1. 本地 prepare 精确候选 context；无 Docker、网络、共享运行态操作。
2. 获 tower 构建窗口后 Docker build；命名保留探针核对三个 app import、版本、静态资产和 apps 注册。不自动改主 runtime/image.env。
3. 共享窗口移交后：先记录运行镜像/服务/卷和合成对象基线；停业务写入及队列，备份数据库、公私文件、必要配置并核对 gzip/tar 完整性、大小和清单，不打印数据。
4. 由 M8/M6 在首次安装前创建新 M8 legacy DocShare fixtures：verify_http.py prepare --legacy-shares；不得在安装后以无 legacy 的 fixture 冒充旁路回归。具体先后由 tower/M8 协调，prepare 后仍须重新备份纳入 fixture。
5. 候选镜像先执行 team_access.install.preflight，发现公共/远程活动附件拒绝，不自动移动或删除。
6. install-app team_access；两次 migrate、clear-cache；所有 Python/worker/scheduler/websocket/frontend/configurator 使用一致安全镜像，核对 site_config 未被覆盖。注销旧会话/清理旧客户端缓存由权限/UI验收负责人执行。
7. M7 导入 smoke、M6/M8 双真实用户权限回归、JS资产/页面/浏览器验证通过后才解除维护。最终 app 合并后按 tower 指令 rebase，重新标准构建与回归完整 deliverable。

## 恢复与导出验收契约

备份与恢复在独占窗口执行，输出只含数量/固定标签/合成 ID，不输出密码、token、encryption_key、客户原文或备份内容。

- 备份：数据库 gzip、公/私文件 tar、site config 四件，检查完整性；受保护私有目录保存 manifest 与校验，禁止提交。
- 恢复隔离：独立项目名、站点名、命名卷、DB 与 Redis；启动前断言不引用源卷、源容器或源网络。端口仅 8089 回环。
- 数据核对：至少 Organization、Contact、Lead、Deal、Task、FCRM Note、Comment、Communication、File、Version、DocShare、Custom Field 的精确数量；业务 ID、Lead 自定义企业/联系人外键、Deal organization/lead/contacts、Task/Note reference、原文 Code 字段与快照、owner/visibility/collaborator/assigned_to 等关联和权限规则。不能只比总行数。
- 文件核对：源备份、公/私文件恢复后逐文件内容摘要与路径；以合成 private/public 附件真实 HTTP 下载读回验证，不向 public 写私文。
- 登录读写：恢复副本真实 Administrator 及现有双 Sales User 密码会话；新增唯一恢复合成记录并读回。执行恢复副本双用户越权与授权撤回，不以管理员 ORM 替代权限验证。
- 受控导出：仅管理员合成数据，明确导出含私域数据的风险；中立 JSON/CSV 以源 ID 保留企业、联系人、需求 Lead、商机、活动/任务及关联表，核对每个外键可追踪。导出不替代 DB/文件备份；普通用户导出权限由 M6/M8 回归。
- 原实例重启：冻结前后快照一致，重启项目业务服务后真实健康/登录/业务关联/原文/权限回归；新建恢复验证记录只留副本，不混入原实例基线。

## 启动、停止与 WSL 生命周期

原入口仍为主 checkout P:/CRM/deploy，runtime 位于其私有 .runtime；开发候选从已登记 worktree 使用经校验的 CRM_DEPLOY_RUNTIME_DIR，不复制或重新生成现站点凭据。

- 原实例正常操作：在第一 Ubuntu 从主 checkout 执行 python3 deploy/manage.py up / status / smoke / stop；stop 不删卷。
- 隔离副本命令与实际恢复步骤待实现并实测后追加，当前不能宣称可复现恢复已完成。
- Docker restart: unless-stopped 仅保证 daemon 活着时恢复容器，不保证 Windows/WSL 长期运行。既有 8 小时 sleep 保活是临时实验，不是正式运行方案。
- 可逆实验操作方式：用户显式打开第一 Ubuntu 终端并保持会话，启动项目后持续运行前台 shell；退出/Windows休眠/WSL终止会影响可用性。正式团队持续运行需独立 Linux 主机或经用户授权的 Windows/WSL 启动托管，尚未交付，不创建未经授权系统服务。

## 已实现但尚未执行的恢复工具

- `compose.recovery.yml`：独立 MariaDB/双 Redis/sites/logs 卷、内部隔离网络、仅 8089 回环。没有 scheduler/worker 服务，禁止副本触发邮件、外部集成或重放排队任务。所有应用服务同不可变镜像。
- `recovery_manage.py check --image <sha256>`：只渲染/检查本地 Compose，不连接 Docker daemon 或源实例；断言服务/卷/镜像/只读绑定白名单、内部网络和端口。
- 后续 `receive --backup-stem <YYYYMMDD_HHMMSS-crm_localhost>`：需要独占窗口、显式 `--confirm-isolated-recovery-window` 和新32位hex `CRM_RECOVERY_RUN_ID`。拒绝已有恢复资源、占用端口、不一致源项目/service/镜像/app；仅源四件已选备份通过 tar 流进入新私有 Docker bundle 卷，不在 Windows 文件系统落秘密；源/接收端逐件SHA私下核对，不打印摘要。原备份保留。
- 新卷、容器、网络必须带精确project/M9/run_id labels；bundle manifest和独立keys卷中的run-id双标记再校验。receive先拒绝同名资源，才创建本轮标记空卷；restore只接受本轮成功接收容器和同标记从未启动过DB/sites的卷，不以同名冒充新目标。任何失败保留现场，不force重试或清理。
- `receive_recovery.py`：只在 network=none 自有命名接收容器运行，四件文件名/大小/SHA/gzip/tar/config 核验，O_EXCL拒绝覆盖；新独立 keys 卷生成高熵恢复 DB root 密码，0400/0600与目录0700，不输出秘密，不把密码放 CLI/env。MariaDB 用 `MARIADB_ROOT_PASSWORD_FILE`，恢复服务只读挂载 keys/bundle；尚未实际生成这些卷。
- `restore`：除既有窗口确认外，必须显式传 `--confirm-synthetic-only-data`；确认由 CLI 经 Compose 仅传入 restore 服务，拒绝 ambient 环境偷渡和渲染结果篡改。恢复脚本同时要求源配置 `team_access_synthetic_only` 严格为整数1，两条件通过后才写新副本并保留该值；缺失/类型错误不默认、不写源、不冒充真实性检测。拒绝现有恢复站点及任何先前启动过的目标数据库容器，原生 Framework `_restore` 同版本恢复 DB 与公私文件。除此确认值，仅继承 encryption_key/backup_encryption_key/导入禁用标志；连接严格写入独立 recovery-db/双Redis，关闭调度、邮件、Server Script，绝不复制源服务连接配置。恢复后 app 集合、preflight 和逐文件内容/清单核对通过才启动副本服务。
- 固定源码核对：Framework `commands/site.py::restore_backup` 内部调用 `_new_site(...source_sql, force=True)`；必须先在独立新 DB 卷/唯一新 DB 名上执行，不能因 CLI 未传 --force 就误称无覆盖风险。`_restore` 原生提取在恢复站点复制并清理**本次临时 tar 副本**；bundle只读、源所有旧备份不动。tower已明确认可仅本任务全新、从未接收业务写入的恢复DB/sites初始化及本次临时tar清理语义；**不是一般删除授权**，实际执行仍待窗口。
- 恢复容器IP与未来backend不同：固定源码 `DbManager.get_current_host()` 用 `select user()`，而restore CLI/`_restore`不暴露`_new_site`的mariadb_user_host_login_scope参数，默认账号仅来自恢复容器IP。因此在新恢复DB内部另建同名站点账号host `%`，密码为新生成值，只授字面固定库 `_crm_recovery_b010200`（转义下划线通配），参数化SQL，不带GRANT OPTION或全局权限，私下核验SHOW GRANTS；与原生IP账号并存，不删除旧账号、不改源DB授权。tower已接受此候选方案，实际grant仍未执行。DB无发布端口，internal网络仅本项目服务加入。
- `capture_state.py --snapshot-run M9...`：只针对两个固定站点的管理员持久化证据工具，不是权限测试。12类对象完整记录/子表摘要、自动 Link/Dynamic Link 关系及缺失引用计数；摘要只存站点 private/recovery-evidence 新0600文件，日志仅计数/断言，不打印摘要/原文。`--export-run M9... --confirm-synthetic-admin-export` 才生成完整 JSON 和逐类型 CSV，置于 private/recovery-exports 新0700目录，拒绝覆盖、公式前缀防护、JSON全文/关系及CSV全字段读回；不导出 User/__Auth/配置/凭据。尚未实际快照/导出业务资料。

恢复工具目前通过全8个部署 Python 的 AST、git diff --check、第一 Ubuntu 本地 Compose 结构检查（精确固定镜像/挂载/卷/网络/端口/run标签，不连接daemon/源实例）。本地配置变异夹具另验证9种错误配置均拒绝：错app镜像、错DB digest、引用源卷名、错挂载目标、可写bundle、额外网络、非internal网络、非loopback端口和额外worker。本地一次性合成夹具验证了正常tar内容摘要、6种不安全archive输入拒绝（错目录、穿越、绝对路径、symlink、特殊文件、重复文件）、JSON/CSV中文/子表/公式转义及拒绝覆盖；首次夹具发现Windows默认编码读回中文不一致，已显式统一UTF-8并重跑PASS，夹具自动清理且无真实业务数据。启动后自有network/container标签、状态、网络与安全镜像核对逻辑、最终候选image revision labels校验仍未实际执行。这些检查不代表通过原生 DB 恢复或登录验证；窗口未授权前不得运行 receive/restore/up/stop/status。最终可复现执行命令和真实结果待窗口中补充。

### 执行前审查候选的离线复核

ab8913f 执行前独审为 clean/hold（无P1/P2，不是合并批准），tower只授权采纳非阻断的archive预检加强：相对路径先用PurePosixPath消去`.`，等价文件路径或文件/目录类型冲突在提取前拒绝，重复的合法目录成员仍兼容。纯内存tar夹具通过空archive、合法目录及规范化内容摘要正例，10个重复/类型冲突/不安全路径反例均拒绝；AST和diff检查通过。未运行原生restore，不把最终inventory失败当提前拒绝。

固定MariaDB digest `f1c56f035ed268a0d7c2c2e06dc879f6319b997cb434cf822a4cfd72a7aa184d` 的本地公开image只读inspect/save流解析证据（不创建/启动容器）显示：默认User未设置即root，mysql账号为999:999；固定入口 `file_env` :36读取_FILE、:38 export值、:39 unset_FILE，`docker_setup_env` :263处理root密码，`_main` :683先调用setup_env，:689才gosu mysql。因此uid1000的0700 keys目录与0400密码文件有静态兼容性依据：root先读，mysql重入继承值无需再次读_FILE；尚未实测实际挂载/初始化，不为UID假说放宽权限。公开入口SHA256 `63eb1c8d22816921a03ba4e3c20a8d8b96ed63aaf8c815d8af0f1a0b946c81da`；忽略目录 `deploy/.runtime/mariadb-fixed-public-evidence/public-manifest.json` 记录digest、层路径和三个公开文件摘要，无秘密或源运行卷。

本候选先提交供安全审查并冻结，不代表M9完成，也不绕过M7/M8依赖门。标准可重复的离线命令如下（第一条在本worktree根目录，第二条只在第一Ubuntu渲染Compose；该image仅用于配置字符串检查，不启动旧镜像）：

```bash
python -B -c "import ast; from pathlib import Path; paths=list(Path('deploy').glob('*.py')); [ast.parse(p.read_text(encoding='utf-8')) for p in paths]; print('PASS AST:', len(paths))"
python3 -B deploy/recovery_manage.py check --image sha256:adab8ed8822747b07d10f3f89fbbd129e163b2de656997d07c9b423224ded73b
git diff --check
```

待实测重点：Docker/MariaDB原生初始化及0400 keys文件读取、精确SHOW GRANTS格式、restore完整路径/配置适配、所有run marker/冲突门在真实资源上的行为、internal网络8089真实访问、原文/业务图及公私文件一致性、双用户真实登录读写与撤权、源重启后状态和受控导出。任何失败都保留原站点、所有备份、卷和本轮现场，不自动清理或换旧安全镜像继续运行。

## 已执行候选构建证据

在 Windows 原生 Python 中准备精确源码（无 Docker）：

```powershell
python -B deploy/prepare_integration.py --resource-commit 746076bfd6ede014739668b7fd20d1e53376569b --access-commit 509df32e33abf477693503bc4c1a8052e476fe6a
```

源码逐 blob 从 commit 读取，拒绝链接/非白名单和私有路径；39个 app/部署源文件及 SHA 写入忽略 context。Dockerfile 专用 ignore 仅放行两 app 和 Dockerfile，不携带 runtime/秘密或 `.tower`。`--context <绝对目录> --build` 支持 Windows准备、第一Ubuntu构建，构建前核对所有文件/摘要及无额外文件，产物锁只写该 context，不动主 `.runtime/image.env`。

实际第二 context：`deploy/.runtime/integration-7f8bb3e1dacd49b1acd1069a6ff952d7`；tower 授权后在第一 Ubuntu 标准 `docker build --network host --progress plain`，传本机授权7897无凭据代理和两来源 revision 参数。原CRM层缓存复用；team_access 首次 --no-build-isolation 因基底没有 flit_core 构建 backend 失败，改回 pyproject 声明的隔离构建 `pip install --no-deps -e` 后通过，无新增运行依赖。离线 bench build --app team_access/资产复制成功，缺 Redis 的离线资产更新警告保留，不需要构建期共享 DB/Redis。

候选 image **sha256:adab8ed8822747b07d10f3f89fbbd129e163b2de656997d07c9b423224ded73b**，tag `crm-local:security-m9-7f8bb3e1`。它仅含初始 M8 509df32，且继承了后述空 Framework manifest 问题，**不是最终可部署权限版**。67f2571 候选静态复审发现两个 P1 后已被 a743fca59d6db06ebc982a7598a2d43b8f35a0ff 集中修订替代；按 tower 指示等待新静态复审与授权再统一重建，不构建旧候选。

`probe_integration.py` 经 stdin 传入自有 `network=none` 命名容器 `crm-m9-offline-probe-7f8bb3e1-r3`，独立命名 sites/logs 卷保留。实测四 app版本/完整apps.txt/两份权限JS镜像资产/Node语法/bench version及restore CLI均PASS；未连接任何DB/网络。先前两个探针分别因 login-shell PATH丢Node、嵌套引号失败而退出，均保留，没有删除重试资源。没有读取共享容器/网络/卷，没有激活运行锁。

按 tower 请求从自有r3探针只读导出固定**公开上游源码**到忽略 `deploy/.runtime/upstream-evidence-7f8bb3e1/`，含 CRM activities/doc/Note/Call integrations 与 Frappe permissions/query/reportview/File/upload/download/docinfo/restore 等，23文件有路径+SHA manifest，另补 crm/integrations/api.py；已交 M8 和独审。未复制 sites/logs/env 或秘密，上游代码不提交本分支。

## M7-only 标准登录资产修复窗口（已完成并释放）

本段是提前修复既有标准登录故障，**不是 M8 安全安装或最终恢复验收**。tower 明确授权 M9 唯一构建和共享部署窗口，M6/M7 期间暂停并发运行态操作。

- 原因：固定 Framework 基底 `assets/assets.json` 有32个映射，而没有 `sites/assets/assets.json`；旧 CRM 构建未预置后者，esbuild 从空对象合并并回写，导致派生镜像两处 manifest 变成 `{}`，虽 hashed 文件存在，Guest `/login` 仍引用无 hash 的 JS/CSS 并返回404。用精确基底与 M7 独立 network=none 探针证实，非 M8 引入。
- M7 修复来源 `c8b870b20099170e05fecb648d6f08201cdd9f77`。`prepare_integration.py --resource-only-commit` 同时从该 commit 提取 Dockerfile、专用 ignore 和 resource_import，context `integration-b9fbb3df92114b0f93bd68bbe97f8609` 共19文件。第一 Ubuntu 真实标准 build 23.5秒，产物 `sha256:c47b7cc4bc53cf6388977eb03dab9a9a1658a1c1fdca0d9a8b5cc89c57bc9411`，tag `crm-local:integration-b9fbb3df92114b0f93bd68bbe97f8609`。自有命名探针 `crm-m9-assets-m7-final-b9fbb3df` 验证 image/sites 两 manifest 各32映射及所有目标、三 app 版本/注册，team_access 未装；探针容器/卷保留。
- 切换前停 frontend/websocket/queue-short/queue-long/scheduler 写入；backend 原生 backup --with-files 生成 `20261031_034520-crm_localhost` 四件：数据库336426字节、公文件10240、私文件10240、config94。gzip完整读、tar成员/普通文件及站点配置逐字节核验通过，备份原件保留于原站点 private/backups；旧镜像锁另存新文件，没有删旧备份或卷。
- 激活新镜像后 configurator/backend/websocket/frontend/queue-short/queue-long/scheduler 全7服务均为该不可变ID，继续使用原 sites 卷 `crm_mvp_v15_sites`，site_config逐字节不变、common config语义不变，运行manifest32项/目标验证通过。未安装 M8，未执行迁移或删除业务数据。
- 首次标准 smoke 仍失败，记录为失败后继续诊断，没有误报完成。本站 clear-cache/clear-website-cache 不能清掉 Framework `get_assets_json` 的**全局共享**精确 `assets_json` 缓存：该缓存仅8个RTL映射，三个标准登录资产key缺失。tower 另行授权后，仅调用 `frappe.cache.delete_value("assets_json", shared=True)`，无 FLUSH/宽匹配删除；重新读取形成32主映射+8RTL=40且无冲突，再清本站 website cache。
- 最终标准 `manage.py smoke` PASS：Guest标准登录页、映射JS/CSS和Content-Type、ping、Administrator真实登录/session、CRM HTML/JS。真实请求 website CSS `M7Z35CSX`、login CSS `J7LAEDYF`、frappe-web JS `ZHGNNN4K` 全200且类型正确，website_script.js200。
- 资源兼容性使用既有 `M7HTTP001` 首行经真实REST preview/apply再次执行，均“已导入”，3组织/4联系人/6Lead数量不变。原全矩阵driver要求全新前缀，故没有拿既有前缀盲跑或新增业务记录。
- 已明确释放共享窗口给 tower/M6 的干净标签页标准登录/视觉验收；M9 此后不追加共享读取或运行操作，等待下一窗口。M7已接收精确shared缓存失效的复现要求；M9最终组合 Dockerfile同步manifest预置及保留断言，尚待最终M8候选重建。

## 实际证据台账

| 门槛 | 当前结果 |
|---|---|
| 初始候选构建/离线静态资产 | 746076b+509df32组合标准build及network=none探针PASS；非最终M8版本且有旧manifest问题 |
| 精确context复核 | Windows/第一Ubuntu --context校验均exit0；M7-only c8b870b精确19文件真实build通过 |
| 恢复配置离线结构检查 | recovery_manage.py check PASS，不连接daemon/源实例；后续加强仍需复核 |
| 备份完整性 | M7-only窗口四件备份核验PASS；最终安全app安装后的恢复备份未执行 |
| preflight / install / migrate 两次 | M8 未执行 |
| 统一镜像/服务健康/导入兼容 | M7-only c47b7cc全7服务一致、配置保留、标准真实登录/资产及既有导入幂等PASS；最终四app版未执行 |
| M6/M8 真实权限回归 | M9最终集成回归未执行 |
| 独立 DB/公私文件/配置 restore | 未执行 |
| 对象/原文/关联/文件核对 | 未执行 |
| 副本真实登录与读写 | 未执行 |
| 受控导出与引用核对 | 未执行 |
| 原实例重启持久化/权限 | 最终安全版未执行；M7-only切镜像不冒充该项 |
| 最终依赖合并、标准复验、独审 | 未执行 |
