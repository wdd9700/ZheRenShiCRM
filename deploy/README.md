# Frappe CRM 固定版本本地实验部署

**状态：可登录CRM基座已真实运行；Windows/WSL健康、登录会话、前端资产和合成Lead写读烟测通过，尚非完整团队MVP。** 仅第一个实验 `Ubuntu-24.04`、仅合成资料、仅回环访问；不是生产上线方案。决策链为 `docs/DECISION_LOG.md` D-001/D-002/D-003。

## 版本与选型

- CRM源码：官方稳定main谱系发布 `v1.90.0`，commit `36bd8859f2a6345a620477bc708d0546e8c3f08a`，非develop/v2。Dockerfile在安装后校验commit及两份上游yarn.lock未变化；Python额外依赖按该commit的pyproject解析，尚非全依赖逐包hash锁定或字节级可复现构建。
- 基底：`ghcr.io/frappe/crm@sha256:c3873edce03a0e9327306092c5f392b182304d905f9286057f90fb5739f810ca`，linux/amd64 child `sha256:7c97745a316a9d33cfd213d96f4c91b6882e7ab917afcf4d6cc20d824f1826da`。真实 `bench version` 为 **frappe 15.125.0**，但官方发布镜像不含crm模块，不能直接部署。
- `deploy/Dockerfile`补入上述固定CRM源码、构建资产及仓库内`resource_import` app，保留官方运行入口。`manage.py build`把实际派生image ID写入git忽略的`.runtime/built-image.env`；仅首次不存在活动锁时以exclusive方式创建`.runtime/image.env`，已有活动锁绝不覆盖。升级须在协调窗口备份并显式激活候选锁。Compose统一用活动不可变ID，`pull_policy: never`，不依赖本地浮动tag运行。
- MariaDB **10.6.28**：`public.ecr.aws/docker/library/mariadb@sha256:f1c56f035ed268a0d7c2c2e06dc879f6319b997cb434cf822a4cfd72a7aa184d`。
- Redis **6.2.24-alpine**：`public.ecr.aws/docker/library/redis@sha256:63d5174750e285bc3069c4519c53c8b6de6ebe70715140a6c9d21d6f04b77319`。
- v15依赖参考[官方安装页](https://docs.frappe.io/framework/v15/user/en/installation)及[历史Docker提交](https://github.com/frappe/frappe_docker/commit/eb3ce8a14698bb7826542d6d9b30342ac8b7da92)明确10.6/6.2。当前Docker拓扑参考提交 `61d35da827ebc04d01b64c9e78385597ccebc9d8`，其11.8/8.6不直接套给v15。初试旧项目`crm-mvp`的11.8/8.6容器和卷全部保留、不复用、不降级数据库目录。
- 本机Ubuntu Docker CLI/Server **29.1.3**；Windows默认Docker pipe不可达，Windows standalone Compose v5.1.1仅作静态交叉检查。初始stable digest `8c758d52f941c0f84f2ebe71e5eec88cf343ef29b9c05a23947a641278821b1e`与发布tag不同，不把二者等同。

Frappe CRM为AGPL-3.0，Framework为MIT；网络提供修改版服务时评估对应源码义务，不把团队内网当免除。Twenty仍是备选，但其行级权限依赖Organization Premium，当前先验证Frappe业务/权限，不因可回退打包故障直接换基座。

## 安全与资源边界

- 只用`Ubuntu-24.04`，禁止进入`Ubuntu-24.04-2`训练环境。用户已授权第一个实验发行版本项目root Docker及必需Compose/镜像复制/构建工具；不改Docker服务、用户组、防火墙或全局代理。
- 最终项目固定`crm-mvp-v15`；卷`crm_mvp_v15_db`、`crm_mvp_v15_redis`、`crm_mvp_v15_sites`。首次部署先查同名资源；已有站点绝不再new-site或重建库。DB/Redis不发布端口，唯一入口`127.0.0.1:8088:8080`。
- 初探54GiB RAM、根卷819GiB空闲；官方release压缩层约779MiB，派生Node依赖/镜像/数据库额外占空间，预留至少5GiB实验预算；不是生产容量建议。
- `init-env`用标准库生成独立高熵DB/管理员密码，O_EXCL拒绝覆盖、不打印值，POSIX创建0600；DrvFS仍须依赖Windows ACL。本地`.env`对Docker管理员可见，不等于生产秘密管理。
- 不提交`.env`、token、客户数据、渲染后的含秘密Compose、OCI缓存、日志、卷或备份。构建上下文现在是仓库根，`deploy/Dockerfile.dockerignore`只放行Dockerfile与`apps/resource_import`源，排除pycache/egg-info；`deploy/.dockerignore`继续拒绝旧式deploy上下文的其他文件。
- 不`down -v`、prune，不清理旧容器/镜像/卷。初始化/探针容器故意保留。仅configurator无状态一次性容器经tower批准可必要重建，保留sites/logs卷；其可写层已核验仅pycache。官方入口重建`sites/assets`镜像资产链接，不删除站点public/private资料。

## 从干净环境复现

在已有Docker daemon、Compose v2、Buildx、Python3的**第一个实验Ubuntu**中，从实际checkout根执行（不使用Windows默认Docker pipe）：

```sh
cd /mnt/p/CRM  # 按实际checkout替换
python3 deploy/manage.py init-env   # 仅首次，已有.env则拒绝
python3 deploy/manage.py build --proxy http://127.0.0.1:7897
python3 deploy/manage.py check
python3 deploy/manage.py pull       # 只拉固定DB/Redis
python3 deploy/manage.py create-site
python3 deploy/manage.py up
python3 deploy/manage.py status
python3 deploy/manage.py smoke
python3 deploy/manage.py smoke-data # 显式写一条合成Lead，再读回；重复调用复用，不删除
```

代理是本机现有、经授权、无凭据回环端点；无代理网络可用时省略`--proxy`。只给build进程传Docker内建代理参数，不写Dockerfile ENV、不禁TLS、不改daemon。构建需公共GHCR、GitHub源码和Python/npm registry网络；脚本不自动安装软件。`build`需先取得固定基底，网络限制环境可用下节标准OCI导入。`check`只输出是否通过，不渲染秘密。

`create-site`仅全新站点一次性使用，固定命名防止误重复。本轮已有Framework站点曾因官方镜像缺crm失败，恢复用`python3 deploy/manage.py install-app`，**不是再次create-site**。该命令也保留固定命名一次性容器；失败应先调查、不要盲目反复执行。

访问 `http://127.0.0.1:8088/crm`，用户`Administrator`；凭据仅留本机，交接后位于私有`deploy/.runtime/.env`，旧部署兼容`deploy/.env`；不要打印或贴出密码正文。`smoke`校验pong、真实登录、会话身份、CRM HTML及JavaScript资产；`smoke-data`再通过登录会话/CSRF和标准REST写读合成Lead，不是业务/团队权限验收。

## 授权安装与下载恢复

使用现有签名Ubuntu源，均先`apt-get --simulate install --no-install-recommends <固定包>`，再安装；无升级/移除、无Docker服务重启：

| 主包 | 固定版本 | 下载/新增磁盘 |
|---|---|---|
| docker-compose-v2 | 2.40.3+ds1-0ubuntu1~24.04.1 | 14.8MB / 66.6MB，单包 |
| skopeo | 1.13.3+ds1-2ubuntu0.24.04.3 | 13.6MB / 69.6MB，含下列依赖 |
| docker-buildx | 0.30.1-0ubuntu1~24.04.1 | 16.8MB / 71.0MB，单包 |

skopeo依赖：containernetworking-plugins 1.1.1+ds1-3ubuntu0.24.04.3、golang-github-containers-image 5.29.2-2、golang-github-containers-common 0.57.4+ds1-2ubuntu0.2、libgpgme11t64 1.18.0-4.1ubuntu4。

Docker Hub直连不可达，DB/Redis采用实际核验RepoDigest的Amazon ECR Docker Official Images源，不声称与Hub digest相同。GHCR直拉900s/600s/180s尝试未完成，获授权后标准skopeo进程代理98.6秒完成：

```sh
mkdir -p deploy/.runtime
HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897 NO_PROXY=localhost,127.0.0.1 \
  skopeo copy --all --preserve-digests --retry-times 1 \
  docker://ghcr.io/frappe/crm@sha256:c3873edce03a0e9327306092c5f392b182304d905f9286057f90fb5739f810ca \
  oci:deploy/.runtime/crm-oci:crm-v1.90.0
skopeo copy --all --preserve-digests oci:deploy/.runtime/crm-oci:crm-v1.90.0 \
  oci-archive:deploy/.runtime/crm-v1.90.0.oci.tar:ghcr.io/frappe/crm:v1.90.0
docker load -i deploy/.runtime/crm-v1.90.0.oci.tar
```

19个blob均逐个SHA256匹配，load后RepoDigest精确匹配；缓存保留。初试未完成Compose下载残片3,650,973字节经tower逐路径批准删除，未执行该残片，后用签名包取代。诊断时曾误用一次`docker run --rm`无名只读探针，自动删除其自身容器及镜像声明的匿名卷，违反保留边界；已立即报告tower并停用，未影响任何项目容器、命名站点/数据库卷或业务数据。后续探针均固定命名保留，未经批准不清理。

## 实测记录与上游问题

- 依赖最终10.6.28/6.2.24真实启动：DB healthy，两个Redis PONG，无对外端口。
- 官方release镜像真实`apps`只有frappe15.125.0，`find_spec('crm')=None`；new-site已建Framework站点但安装crm报ModuleNotFoundError。
- [CRM workflow固定commit](https://github.com/frappe/crm/blob/36bd8859f2a6345a620477bc708d0546e8c3f08a/.github/workflows/builds.yml)仍传APPS_JSON_BASE64 build-arg，[Dockerfile固定commit](https://github.com/frappe/frappe_docker/blob/61d35da827ebc04d01b64c9e78385597ccebc9d8/images/layered/Containerfile)只接受apps_json secret：接口不匹配已核对；造成此发布缺app是高置信推断，未还原全部当次CI。未对外提交issue。
- D-003选择最小派生而非未知旧镜像。前两轮host网络构建在Framework默认Redis 127.0.0.1:13311超时；清空构建common并非解决原因（基底本就为空）。最终仅资产RUN设network=none，走官方缺Redis时的离线容错，Vite3315模块/PWA/翻译16.5秒成功；源码/依赖层与两份yarn.lock未改断言通过，未改上游代码。
- 最终派生镜像ID：`sha256:2408974e8c5b8f3feacbaf6cac3c62e69c41fe1cf10dec251dd6cbdd1b9de5f3`；config blob `sha256:6927261196a9d396aaad8860d8879616132a9ea0606bf3c9a52a3181604488ff`。真实import crm=1.90.0，运行bench version crm1.90.0/frappe15.125.0。
- configurator重建前：旧image为c3873...、exit0，project/service准确；sites=`crm_mvp_v15_sites`，logs匿名卷`e773448202e999668f51482862f9b781e1d9cb48990ed5de37b94f9246588fe3`，可写层仅pycache。重建后exit0，site_config前后SHA256均`5323a962331bfd2f667cd3a7a9ae7173b68fc2a810d35a705ac9a217339cfd11`；common保留db_host/db_port/redis_cache/redis_queue/redis_socketio/socketio_port/chromium_path，连接值断言正确，apps.txt为crm/frappe；不覆盖空配置。
- 原站点`install-app crm`全部DocType及自定义字段安装成功、exit0；`up --wait`成功，9长驻服务运行，DB healthy、两Redis PONG。应用服务无自定义Docker healthcheck，Compose显示Healthy仅表示running，**应用健康另由实际HTTP烟测证明**。旧失败create-site与探针仍保留，不能误判为当前服务故障。
- WSL `smoke-data`与Windows `smoke`真实通过：ping pong、Administrator密码登录、会话身份、CRM HTML和两份JavaScript资产HTTP200。标准REST/CSRF创建并读回中文合成Lead `CRM-LEAD-2026-00001`；再次执行复用同ID、未重复创建、未删除。最初CSRF解析未适配`window["csrf_token"]`曾失败，修正后最终脚本已通过。
- Windows和WSL访问路径都已验证；浏览器视觉/JavaScript交互未实测（内置浏览器当时不可用），不能把HTML/资产200当完整UI通过。

### WSL临时保活

曾观察容器StartedAt随短WSL调用变化、RestartCount=0，Docker ActiveEnterTimestamp也更新；尚未证明是WSL空闲退出还是Docker生命周期变化。2026-10-31 03:42:40+08获tower批准启动仅第一发行版的有限保活：`wsl.exe -d Ubuntu-24.04 --exec /bin/sh -lc 'exec sleep 28800'`。任务`bash-8c1k70ne`、Windows PID65128、Ubuntu PID2262，预计**11:42:40+08到期**，非生产服务机制；到期后短WSL命令结束可能再次失去持续访问。未修改.wslconfig或服务。保活后03:42:48与03:44:51两次检查后端/前端/DB StartedAt均保持19:42:21Z、RestartCount0，Windows HTTP通过。

开发时可保持第一Ubuntu终端活动并运行`python3 deploy/manage.py up`后烟测；勿重复启动保活进程，先检查已有PID。迁移到正式持续运行服务方式后才撤掉临时保活。

### 运行材料交接：合并后、清理工作树前的强制门槛

Git合并不搬运忽略的运行材料。**后续正式运行入口是主checkout `P:/CRM/deploy`，不能长期依赖wt-3。以下实际交接必须在本修复合并后执行；预合并只允许在私有fixture演练，fixture成功不代表主checkout已交接。** 未完成全部门槛不得清理源工作树或继续把迁移标为完成。

在本机Windows原生Python中，从保留的源部署目录显式执行（不通过WSL运行交接命令）：

```powershell
python P:\CRM\.tower\worktrees\wt-3\deploy\manage.py handoff-runtime --target-dir P:\CRM\deploy
```

- 只将现有凭据文件（优先源`.runtime/.env`，兼容旧`deploy/.env`）与`.runtime/image.env`按不透明字节复制到**目标`deploy/.runtime/.env`与`deploy/.runtime/image.env`**；不解析或输出正文，不输出摘要，不经网络，不生成新密码，不复制数据库/缓存/产品代码，不删除或修改源文件。
- 目标必须是本地固定磁盘上的绝对`deploy`目录、位于Git根下；三个部署代码文件必须已跟踪且与源版本一致，因此必须先正常合并，工具不会预合并改主checkout。两份目标运行材料逐个验证Git忽略且未跟踪；拒绝链接/junction/reparse点、硬链接及异常路径。
- PowerShell辅助脚本只创建专用私有`.runtime`目录和文件，DACL关闭继承，仅当前Windows SID、SYSTEM、Administrators可访问；**不修改跟踪的deploy目录或递归ACL**。检查父目录不能让其他主体删除/替换私有目录或夺取其权限；不满足则失败，不扩大权限绕过。
- 已有安全且字节一致的目标材料保持原样，可重复交接；任一异值、不安全目标文件或旧目标`deploy/.env`均拒绝，不静默覆盖/合并/遮蔽。若只有已存在的空`.runtime`目录继承ACL不安全，可显式追加`--secure-runtime-dir`，仅收紧该目录自身、不递归或修改已有文件ACL；不是忽略文件冲突的开关。冲突需先由tower核实，不重新初始化、不自行删除文件。
- 创建用带私有ACL的`CreateNew`及排他文件句柄，内部核对复制前后字节一致。失败可能留下受保护的部分目标；保留两端供调查，不自动删除或覆盖重试。
- 复制后命令自动从**目标manage.py**运行Windows `check`及`smoke`，只报告步骤PASS/失败，不转发子进程正文。两步全通过才报告handoff成功。目标使用私有`.runtime/.env`，旧源`deploy/.env`仍兼容；不要手工另建一份凭据使入口混乱。

合并后交接记录必须逐项写明（不含秘密、摘要或会话）：

1. 合并后的目标代码版本、源/目标路径，以及上述handoff命令返回0、目标Windows `check`和`smoke`均PASS。若失败，停止交接，保留源；**对现有卷禁止`init-env`、`create-site`/`new-site`或重新生成密码**。
2. 从目标主checkout执行以下第一Ubuntu只读验收，确认Windows私有ACL没有阻断WSL。不能用Everyone权限放宽来修复失败：

   ```sh
   MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 --exec /bin/sh -lc 'cd /mnt/p/CRM && python3 deploy/manage.py check && python3 deploy/manage.py smoke'
   ```

3. 从第一Ubuntu的目标checkout运行`python3 deploy/manage.py status`，核验仍为`crm-mvp-v15`及原镜像/命名卷、入口仍是`127.0.0.1:8088`；Windows默认Docker daemon不可达，不把Windows `status`当运行态入口。不重建站点、不重启服务来制造验收成功。确认两端文件保留、目标材料未被Git跟踪或提交。
4. tower记录以上真实主checkout结果并明确后续任务改用`P:/CRM/deploy`；完成前源worktree必须保留，完成后是否清理仍按原删除授权流程决定，工具本身从不清理。

本轮私有Git fixture已验证：真实复制后目标Windows与WSL `check/smoke`通过、目标Ubuntu `status`仍看到原项目；重复交接两文件字节/mtime不变，源字节与第一次安全副本相同且原时间戳保留，公共deploy目录ACL前后不变。异值、单一路径未忽略、已跟踪材料、代码不匹配、相同/相对目标、硬链接、正常及断裂junction、不安全已有文件/目录以及父DeleteChild权限均被拒绝；显式仅收紧`.runtime`后Windows/WSL仍可读。最终版本还在含空格路径、公开部署代码为Git CRLF checkout的目标真实交接成功，并通过目标Windows/WSL `check/smoke`：代码比较仅规范化LF/CRLF，实际运行材料始终保持原字节。脚本正文/摘要未输出。首次fixture最后误用Windows `status`未通过，改为实际Ubuntu运行入口后通过；另一次测试捕获Docker Unicode输出遇GBK解码，改验证器UTF-8捕获后通过，均未改服务或放宽ACL。

验证材料保留在忽略的`deploy/.runtime/`下：`handoff-r1-20261031-040740/`、`handoff-r1-cases-20261031-041011/`、`handoff-r1-final-20261031-041606/`以及最终CRLF/空格路径目标`handoff-r1-crlf-20261031-041736/checkout with spaces/deploy/`。成功副本均使用私有ACL，不提交、不作为正式入口。

**实际主checkout交接和上述四项验收仍是合并后必做、尚未执行的交付门槛。** fixture成功不代表实际迁移已完成，不得据此清理wt-3。

## 后续业务任务的只读入口

固定运行源码只读核对（JSON reqd不是全部业务校验）：

| 实际DocType | 关键字段/关联 |
|---|---|
| CRM Lead | first_name、status必填；status→CRM Lead Status，lead_owner→User；organization是Data非企业外键 |
| CRM Organization | organization_name；industry/territory/address为Link；JSON未标必填 |
| Contact | Framework原生；first_name/last_name，email_ids/phone_nos子表，links→Dynamic Link |
| CRM Deal | status必填→CRM Deal Status；organization→CRM Organization，lead→CRM Lead，contacts→CRM Contacts→Contact |
| CRM Task | title必填；assigned_to→User，reference_doctype/reference_docname动态关联，due_date Datetime |
| FCRM Note | 不是CRM Note；title必填、content、动态reference关联、pinned/by/on |

前五者allow_import=1；前端已有`/crm/data-import`及`/crm/data-import/doctype/:doctype?`路由、SetupImport上传/映射/复核组件，但本轮未验收导入。`assets/locale/zh/LC_MESSAGES/crm.mo`存在，只证明中文翻译产物，不保证默认语言或汉化覆盖。

无需读`.env`的已实测只读命令（第一Ubuntu内）：

```sh
docker exec crm-mvp-v15-backend-1 bench --site crm.localhost execute frappe.get_installed_apps
# 返回 ["frappe", "crm"]
```

受控脚本也可经`docker exec -i -w /home/frappe/frappe-bench/sites crm-mvp-v15-backend-1 ../env/bin/python`输入，在Python中`frappe.init(site="crm.localhost", sites_path=".")`、`frappe.connect()`后用ORM；不打印conf/秘密，不做未经协调的写入，必要写入显式commit，finally destroy。后续业务任务待tower协调共享数据库写入；不能把容器管理员权限当双账号权限验证。

## 停止、回退与未完成边界

`python3 deploy/manage.py stop`只停止本项目、不删卷。后续用`bench --site crm.localhost backup --with-files`，在**同版本新站点真实恢复**并核对公私文件后才能切换；中立CSV保留来源ID，但不能替代数据库与文件备份。

完整MVP后续必须验证：六列中文映射、重复/错误行幂等、企业/联系人关系、需求→Deal、沟通/任务时间线、双账号UI/API私域与共享权限、重启持久化、导出关系与同版本备份恢复。当前不接真实资料、不宣称这些已完成。Web/PWA优先，Electron不覆盖移动端；四端原生包/签名、移动布局、生产HTTPS/身份与升级策略均未验收。

## 六列网页导入扩展（M7）

实现与权限取舍详见 `docs/IMPORT_APP.md`、D-004。入口 `/resource-import`，当前仅System Manager/Administrator；普通Sales User/Sales Manager均不开放。姓名/解析联系值将进团队共享企业/Contact，页面独立默认未勾选的共享确认是强制条件。不同意共享时明确阻止（尚不支持仅私域Lead模式）；只用合成资料。原文不写共享Organization或FCRM Note，只写Lead。

构建（仅镜像，不更新现有活动image lock，不重启服务）：

```sh
cd /mnt/p/CRM # 或本任务worktree
python3 deploy/manage.py build --proxy http://127.0.0.1:7897
# 专用Dockerfile ignore优先于根ignore，只有app源与Dockerfile进入上下文
# 可选预备兼容回退镜像；固定旧CRM镜像必须已在本机，不自动拉未知tag
# 旧CRM本体不含app，不能在站点安装app后直接切回它
OLD_IMAGE=sha256:2408974e8c5b8f3feacbaf6cac3c62e69c41fe1cf10dec251dd6cbdd1b9de5f3
docker tag "$OLD_IMAGE" crm-local:resource-import-compat-base
test "$(docker image inspect crm-local:resource-import-compat-base --format '{{.Id}}')" = "$OLD_IMAGE"
DOCKER_BUILDKIT=1 docker build --network none --pull=false -f deploy/Dockerfile.compat -t crm-local:resource-import-compat .
# 显式复用现有私有runtime（路径须绝对且通过普通文件/非链接守卫），不复制或回显凭据：
CRM_DEPLOY_RUNTIME_DIR=/mnt/p/CRM/deploy/.runtime python3 deploy/manage.py check
```

已有共享实例升级**必须由tower协调M6停止验证/写入，并记录窗口后才执行**：

1. 记录当前运行所有app服务镜像ID，保留旧镜像及活动`image.env`的exclusive备份；不覆盖旧备份。执行`docker exec crm-mvp-v15-backend-1 bench --site crm.localhost backup --with-files`，核对数据库/公私文件备份已存在（内容与摘要不贴日志）。备份创建不等于恢复演练通过。
2. 核对候选`built-image.env`中的ID与实际构建对应。显式将候选活动锁激活（构建命令不替操作者做这一步）；先`manage.py check`，再`manage.py up`重建Python服务及frontend/websocket/configurator等共享同镜像服务。不可只重启backend而遗留旧worker模块路径。此步有短暂维护窗口。
3. 运行`docker exec crm-mvp-v15-backend-1 bench --site crm.localhost install-app resource_import`（仅首次），随后`bench --site crm.localhost migrate`、`clear-cache`。版本化迁移只add缺失字段/唯一索引、遇字段冲突拒绝；已有数据和M5备注不变。重新migrate用于幂等检查。
4. `manage.py smoke`核验原CRM，再显式运行下方HTTP合成核验。普通用户拒绝/浏览器视觉及下载由tower协调M6/浏览器验收；未完成不得标记完成。
5. 回退优先`bench --site crm.localhost set-config -p resource_import_disabled 1`并`clear-cache`关闭入口（`-p`确保JSON数值，不使用真值非空的字符串`"0"`），保留app记录、字段和全部资料，切到预备兼容回退镜像ID（旧CRM+可加载app包），重建同组服务。**不uninstall-app，不删Custom Field，不切缺app的旧镜像，不删卷/合成记录。** 修复后显式`set-config -p resource_import_disabled 0`再clear-cache。数据库恢复必须另行审批并在新站点演练，不在此流程中冒险覆盖现库。

HTTP操作核验（需要现有部署runtime，仅程序内部使用现有登录材料、不打印凭据；显式写入并保留M7合成资料）：

```sh
python3 deploy/verify_resource_import.py --runtime-dir /mnt/p/CRM/deploy \
  --prefix M7UniqueRun001 --confirm-synthetic-write
```

核验覆盖匿名/登录页、POST/CSRF、预览无业务写入（仅短期Redis receipt）、共享/确认/文件来源篡改/缺失/跨会话receipt校验、逐行错误、失败回滚无企业孤儿、重复/并发双会话、原文/来源/完整hash、显式消歧与原生对象链接。每次使用新前缀；不会删除旧验收数据。此脚本不等于浏览器视觉/真实文件控件/失败CSV下载验收，也不等于非管理员实际会话或备份恢复验证。

M7窗口实测：旧镜像`2408974e...`和主私有`pre-m7-image.env`保留；with-files新备份数据库非空+公/私tar+site config四件最近生成已核对，未恢复。安装中patch manifest漏pre_model_sync节、www controller应使用下划线、本站无encryption_key及Long Text会清洗HTML均经真实检查发现并修正，未通过时未宣称完成。最终14字段只增（保留五个早期Long Text，新导入只写五个Code verbatim原文；不变更字段类型/全局过滤器），两次migrate、实际唯一索引及HTTP矩阵核验见IMPORT_APP。当前候选`sha256:36a89c9b0ad6eae3842ba4a32c7c54cfa45c6a7c135041893ba55b9f2f07e238`、兼容回退`sha256:6490855bc7f8e2a78523ac40ad3b5b024d745965ac9c2e834c3bfa9b10641fe9`；M7HTTP001保留3企业/4联系人/6Lead。网页视觉和非管理员实会话待tower协调，不把管理员HTTP通过当完整MVP。

## 官方证据

- [CRM安装stable路径](https://docs.frappe.io/crm/introduction/installation) / [v1.90.0发布](https://github.com/frappe/crm/releases/tag/v1.90.0)
- [Docker拓扑参考](https://github.com/frappe/frappe_docker/commit/61d35da827ebc04d01b64c9e78385597ccebc9d8)
- [Docker Library MariaDB](https://github.com/docker-library/official-images/blob/master/library/mariadb) / [Redis](https://github.com/docker-library/official-images/blob/master/library/redis)
- [Amazon ECR Docker Official Images](https://gallery.ecr.aws/docker)
- [CRM许可证AGPL-3.0](https://github.com/frappe/crm/blob/v1.90.0/LICENSE)
