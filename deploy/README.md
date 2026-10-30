# Frappe CRM 固定版本本地实验部署

**状态：可登录CRM基座已真实运行；Windows/WSL健康、登录会话、前端资产和合成Lead写读烟测通过，尚非完整团队MVP。** 仅第一个实验 `Ubuntu-24.04`、仅合成资料、仅回环访问；不是生产上线方案。决策链为 `docs/DECISION_LOG.md` D-001/D-002/D-003。

## 版本与选型

- CRM源码：官方稳定main谱系发布 `v1.90.0`，commit `36bd8859f2a6345a620477bc708d0546e8c3f08a`，非develop/v2。Dockerfile在安装后校验commit及两份上游yarn.lock未变化；Python额外依赖按该commit的pyproject解析，尚非全依赖逐包hash锁定或字节级可复现构建。
- 基底：`ghcr.io/frappe/crm@sha256:c3873edce03a0e9327306092c5f392b182304d905f9286057f90fb5739f810ca`，linux/amd64 child `sha256:7c97745a316a9d33cfd213d96f4c91b6882e7ab917afcf4d6cc20d824f1826da`。真实 `bench version` 为 **frappe 15.125.0**，但官方发布镜像不含crm模块，不能直接部署。
- `deploy/Dockerfile`补入上述固定CRM源码、构建资产，保留官方运行入口。`manage.py build`把实际派生image ID写入git忽略的`.runtime/image.env`；Compose统一用这个不可变ID，`pull_policy: never`，不依赖本地浮动tag运行。
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
- 不提交`.env`、token、客户数据、渲染后的含秘密Compose、OCI缓存、日志、卷或备份。`.dockerignore`只允许Dockerfile进入构建上下文。
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

访问 `http://127.0.0.1:8088/crm`，用户`Administrator`；密码仅在本机`deploy/.env`的`ADMIN_PASSWORD`安全查看，勿贴聊天。`smoke`校验pong、真实登录、会话身份、CRM HTML及JavaScript资产；`smoke-data`再通过登录会话/CSRF和标准REST写读合成Lead，不是业务/团队权限验收。

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

开发时可保持第一Ubuntu终端活动并运行`python3 deploy/manage.py up`后烟测；勿重复启动保活进程，先检查已有PID。迁移到正式持续运行服务方式后才撤掉临时保活。合并代码不会搬运原工作树忽略的`.env`/image.env，后续任务应使用`P:/CRM/.tower/worktrees/wt-3/deploy/`的本地运行材料；不要复制秘密进Git。

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

## 官方证据

- [CRM安装stable路径](https://docs.frappe.io/crm/introduction/installation) / [v1.90.0发布](https://github.com/frappe/crm/releases/tag/v1.90.0)
- [Docker拓扑参考](https://github.com/frappe/frappe_docker/commit/61d35da827ebc04d01b64c9e78385597ccebc9d8)
- [Docker Library MariaDB](https://github.com/docker-library/official-images/blob/master/library/mariadb) / [Redis](https://github.com/docker-library/official-images/blob/master/library/redis)
- [Amazon ECR Docker Official Images](https://gallery.ecr.aws/docker)
- [CRM许可证AGPL-3.0](https://github.com/frappe/crm/blob/v1.90.0/LICENSE)
