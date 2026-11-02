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
- 不提交`.env`、token、客户数据、渲染后的含秘密Compose、OCI缓存、日志、卷或备份。基座构建入口的`deploy/Dockerfile.dockerignore`只放行Dockerfile与两个app源；新前端入口使用独立的`Dockerfile.frontend.dockerignore`，只再放行after校验器及apply/manifest/payload，均排除pycache/egg-info。精确集成context先由Git白名单导出再逐件核SHA，不直接使用整个运行目录；`deploy/.dockerignore`继续拒绝旧式deploy上下文的其他文件。
- 不`down -v`、prune，不清理旧容器/镜像/卷。初始化/探针容器故意保留。仅configurator无状态一次性容器经tower批准可必要重建，保留sites/logs卷；其可写层已核验仅pycache。官方入口重建`sites/assets`镜像资产链接，不删除站点public/private资料。

## C011000 前端补丁候选入口（source已受控更新，HTTP续验待审）

2026-11-03后续窗口：tower已另授权仅两个本地独立合成站逐站备份更新，不能把下段构建阶段的“未部署”当最新状态。source新四件备份`20261102_235948-crm_localhost`全读验证后，仅三app定点更新至f43a277d；DB/Redis、卷/config、主M7锁及其他容器不变，更新前后12类原文与141引用完全一致。普通Sales原基础矩阵通过；列表验收三次停止涉及脚本不适用前提（Comment未审视图入口403、B共享Lead未必进入原生列表、A额外旧Lead已有明确授权），未修改权限凑绿。**source三app现按失败停写，recovery尚未更新，未执行本候选六服务重启；完整双站结果未通过。** 双账号维护READ ONLY原生/兼容/底层列表集合已全等且逐ID明确授权；共享A Lead对B可直读但默认列表不可发现为独立产品缺陷，不能称共享列表可用。统一续验helper待tower独立复核，不盲目重启。详情及全部失败证据见`docs/RECOVERY_VALIDATION.md`；未新导出release、未远端传输/更新。

`Dockerfile.frontend` 是 M19 缓存隔离的独立候选配方；旧 `Dockerfile` / `manage.py build` 仅保留基座兼容路径，**不包含 C011000 补丁，不可替代新安全候选交付**。2026-11-03，M19精确`1f48ddae07a09c8f0c09aaae6b9a55779dcfdab1`独审clean/merge（旧1c66首审返工记录保留），接入`58a0fd68e630ad06ea07dd6b332c1cbb8956f071`限定clean/hold；tower另授权第一Ubuntu构建/独立none probe，未授权更新任何站点或远端。原四源/69件context receipt不变，标准构建与before/check/apply/after/guard、资产强断言通过；新index `sha256:f43a277d62eab434ba90922f36b8a75e86a99a7d0dbdede1cbb70bbe57783a6d`，config `sha256:50836b19cb4ac574f53840c100123f87f19032c22788cbd63b12f2146537a69d`。完整Linux依赖原生Vitest 34文件/326项通过，另实际bridge 1项通过（只是受控Node18包装），独立probe exited0并保留新两命名卷。标准save只读流核镜像原始摘要链和四label通过，不落tar、不load；所有48个旧容器所选状态/挂载及主活动锁最终不变。命令、完整身份与警告见 `docs/RECOVERY_VALIDATION.md`。**仍需另开本地站点更新窗口与M18固定资产真实UI验收，不能自行部署或传远端。**

纯源码准备（从本 checkout，所有参数必须为已审完整40位commit）：

```sh
python -B deploy/prepare_integration.py \
  --resource-commit faa5f0330ad54bd9f4d02bb498ea305651c95ed9 \
  --access-commit 6b70971f0ac12b2e96b959a61a4c8346eb0868e1 \
  --frontend-commit FINAL_REVIEWED_M19_40HEX \
  --deployment-commit REVIEWED_DEPLOY_40HEX
```

- 新入口只从各精确 Git commit 导出普通 blob，不拼接其他工作树或未提交文件。`source-manifest.json` 记录四个commit与每件SHA；前端白名单是12件或完整15件（后三件为受控消费者fixture，半套/额外文件拒绝），部署白名单仅专用Dockerfile/ignore/after校验器。旧两种context继续兼容。
- 记录输出的绝对 `integration-<uuid>` 路径与 **source-manifest SHA256**。Windows准备后可用WSL路径重读：`python3 -B deploy/prepare_integration.py --context /mnt/p/.../integration-<uuid> --context-sha256 <原输出64位SHA>`；只校验，不构建。前端context没有原摘要、manifest漂移、缺件/多件、链接/硬链接、逐文件SHA漂移均拒绝。未来获准才附加 `--build`（必要时既有loopback `--proxy`），不可重新计算漂移后的摘要来绕过门禁。
- 完整依赖准备：固定c3873 Framework基底→既有 `bench get-app` 与锁/CRM HEAD断言→两个扩展pip安装→M19 `apply --check`→apply→七件after与五件guard复核→原Framework资产preseed→标准 `bench build --app crm` 与资产强断言→team_access资产build→再次after/guard复核。应用后没有pip/yarn依赖安装，不允许手工增加reinstall。
- 既有fb00构建日志的依赖层命中缓存，仅凭CRM HEAD/rc2版本号不能断言干净重建必然得到相同before SHA。任何before不符立即停，不改M19 manifest、不重装包凑通过；M17的39件公开证据不是完整node_modules。当前没有继承/复制fb00镜像作为构建输入，若需要改此设计，先记录决策/可重复条件并独审，不能临时静默换基线。
- 镜像成功后才记录不可变ID和四个revision label；`build-result.json`另记原source-manifest摘要，不修改活动镜像锁。`probe_integration.py`对带C011000目录的镜像追加after/guard复核；原四app/双Framework manifest/全部资产/Node/restore CLI断言不变。
- 后继必须在完整Linux依赖副本跑原 `yarn test:run`、M19 Vitest bridge及标准build，再独立probe、M18固定资产真实账号切换/撤权/后台与多标签UI；受控Node测试和源码重放不替代这些门槛。详见 `docs/RECOVERY_VALIDATION.md` 与 M19 `docs/FRONTEND_CACHE_C011000.md`。

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
# 首次站点：先完成下方“站点错误响应安全基线”，再进行烟测/业务验收
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
4. 完成下方“站点错误响应安全基线”，再用`manage.py smoke`核验原CRM并显式运行HTTP合成核验。普通用户拒绝/浏览器视觉及下载由tower协调M6/浏览器验收；未完成不得标记完成。
5. 回退优先`bench --site crm.localhost set-config -p resource_import_disabled 1`并`clear-cache`关闭入口（`-p`确保JSON数值，不使用真值非空的字符串`"0"`），保留app记录、字段和全部资料，切到预备兼容回退镜像ID（旧CRM+可加载app包），重建同组服务。**不uninstall-app，不删Custom Field，不切缺app的旧镜像，不删卷/合成记录。** 修复后显式`set-config -p resource_import_disabled 0`再clear-cache。数据库恢复必须另行审批并在新站点演练，不在此流程中冒险覆盖现库。

### 站点错误响应安全基线（新站点必做；已有实例须协调窗口）

固定Frappe15.125.0的`System Settings.allow_error_traceback`默认1，会把部分Framework前置异常的堆栈返回浏览器。**首次`up`后、任何烟测/业务验收与业务资料写入前，必须将本站该项正常保存为0。** 已有实例先由tower指定唯一操作者并暂停其他验证/写入；本设置影响本站所有HTTP错误响应，不只是导入，不影响其他站点。现有导入镜像无需重建或重启；这不是app迁移自动配置。

1. 以本站Administrator/System Manager打开`/app/system-settings`，在Advanced/Telemetry找到 **Show Full Error and Allow Reporting of Issues to the Developer**。只记录这个复选框原值，不导出整份设置或site config。
2. 取消勾选并Save，让官方System Settings正常校验及保存；不要用`bench set-config allow_error_traceback 0`，该同名site_config键不被`get_system_settings`读取，也不要以developer_mode=0替代。若使用已授权bench console，等价操作只取单项并正常保存（不输出整个doc）：

   ```sh
   docker exec -it crm-mvp-v15-backend-1 bench --site crm.localhost console
   ```

   ```python
   settings = frappe.get_doc("System Settings")
   previous_traceback = int(settings.allow_error_traceback or 0)
   print(previous_traceback)  # 仅记录这一个非敏感旧值，用于回退
   settings.allow_error_traceback = 0
   settings.save()
   frappe.db.commit()
   exit()
   ```

3. 第一Ubuntu中运行`docker exec crm-mvp-v15-backend-1 bench --site crm.localhost clear-cache`，再重新读取同一复选框确认0。不得读取/打印site_config或凭据来核验。
4. 由独立验证者用合成账号重新测试：先正常preview，再禁用该账号并沿用原会话/有效receipt apply；Framework应仍拒绝401/403/417、无业务写，响应不得有真实`exc`/`exception`堆栈、文件路径/行号、调试内容、候选/私密正文。官方V1无条件保留纯`exc_type`（例如ValidationError），tower明确允许纯类型名；历史失败和断言更正原因须保留，不能静默把旧FAIL改PASS。恢复合成账号enabled；角色撤回是另一条负例，不能用禁用替代。
5. 回退只能在新协调窗口，把这一个复选框恢复步骤1记录的原值、正常Save并clear-cache；若原值1会重新允许向客户端显示堆栈，必须显式评估，不把回退当常态。不要修改其他设置或全局DocPerm。

日志影响不能声称完全不变：关闭会跳过`report_error`中`errprint`的request-local错误列表追加及条件stdout输出，客户端`exc`/异常末行和debug内容减少。`app.handle_exception`对>=500的`log_error_snapshot`独立于此开关，仍按异常排除规则记录服务端Error Log；417本来不进入该snapshot分支，不保证它已有持久堆栈日志。已启用的`enable_frappe_logger`请求访问日志独立，不自动启用额外日志、遥测或外部上报。需要新的安全审计日志时另行设计，不为保留调试方便重新暴露堆栈。

固定官方源码：[Session校验](https://github.com/frappe/frappe/blob/v15.125.0/frappe/sessions.py)、[请求顺序与错误分支](https://github.com/frappe/frappe/blob/v15.125.0/frappe/app.py)、[响应开关与exc_type](https://github.com/frappe/frappe/blob/v15.125.0/frappe/utils/response.py)、[get_system_settings/errprint](https://github.com/frappe/frappe/blob/v15.125.0/frappe/__init__.py)、[官方字段及默认值](https://github.com/frappe/frappe/blob/v15.125.0/frappe/core/doctype/system_settings/system_settings.json)、[服务端snapshot](https://github.com/frappe/frappe/blob/v15.125.0/frappe/utils/error.py)。

### 标准登录资产交付门槛

已确认原M3→M7资产步骤存在缺陷：base根`assets/assets.json`有32键，但`sites/assets/assets.json`不存在；直接CRM-only build生成{}，再复制回根assets覆盖Framework映射。Framework hash文件本身仍在，Jinja缺映射才回退请求裸`/frappe-web.bundle.js`404。M9隔离network=none探针已对比base与M7确认，M8未加入，不归咎后续权限包。此前API登录/CRM Vite资产烟测漏掉标准/login，不能将其视为网页登录通过。

规范Dockerfile在CRM build前将官方烤入assets预置到sites/assets，让官方esbuild合并既有映射，build后断言关键4bundle、全部旧键未丢及映射文件真实存在；不手写hash映射、不重新编Framework。`manage.py smoke`现在先用Guest访问/login，要求Framework哈希JS/CSS且逐一返回正确Content-Type，再测API认证和CRM资产。该HTTP检查仍不能代替JavaScript交互。

修复镜像由单一构建操作者产出不可变ID；仍按上述维护窗口保留旧镜像/lock和备份，统一更新同组服务。**镜像资产更新后必须精确失效bench共享的`assets_json`，仅本站`clear-cache`/`clear-website-cache`不足。** 固定v15.125.0的`frappe.utils.get_assets_json`用`shared=True`缓存主/RTL映射，磁盘已修好也可能继续返回旧映射。此步骤影响同一bench各站点的公共静态资源映射，必须在协调窗口由唯一操作者执行，不能扩展为清空Redis、flushdb、通配删除或删除会话/receipt。

第一Ubuntu内进入已部署backend的本站console：

```sh
docker exec -it crm-mvp-v15-backend-1 bench --site crm.localhost console
```

```python
frappe.cache.delete_value("assets_json", shared=True)
exit()
```

随后运行`docker exec crm-mvp-v15-backend-1 bench --site crm.localhost clear-website-cache`，用新的Guest请求/会话跑`manage.py smoke`；不能只验磁盘JSON或HTTP200，登录页引用的Framework哈希JS/CSS必须真实200且类型正确。不打印整个cache/conf，不手写映射。官方[get_assets_json](https://github.com/frappe/frappe/blob/v15.125.0/frappe/utils/__init__.py)与[Redis包装器](https://github.com/frappe/frappe/blob/v15.125.0/frappe/utils/redis_wrapper.py)是该精确shared键依据。

M9已从精确提交`c8b870b20099170e05fecb648d6f08201cdd9f77`标准构建并部署M7-only镜像`sha256:c47b7cc4bc53cf6388977eb03dab9a9a1658a1c1fdca0d9a8b5cc89c57bc9411`，未安装M8。隔离probe双manifest各32键、关键4bundle及全部目标存在。运行首次smoke仍失败：Redis共享旧值只有8个RTL键；经tower逐项授权只删除上述精确共享键并清本站网页缓存后，重新生成主32+RTL8=40键、无覆盖冲突，完整Guest/login资产与管理员登录/session/CRM smoke PASS。7个同镜像app/configurator服务含frontend一致，原sites卷保留，site_config字节及common配置语义不变；新完整备份stem`20261031_034520-crm_localhost`已核验gzip/tar/config，旧锁与镜像保留，未恢复现库。既有M7HTTP001首行preview/apply均已导入、3企业/4联系人/6Lead不变，没有再全跑要求新前缀的原矩阵。

M6证据提交`93426e65c5f4a2b79dc2922f99ff8ace337f125a`记录新干净Edge tab776603395原生/login填写及点击、未改DOM/未注入sid，`m7-visual.csv`preview200，旧资产404阻断解除。M7随后沿用该标准会话，真实上传新唯一`m7-standard-ui.csv`，共享确认→preview→独立显式确认→apply仅一次：M7STANDARDUI001成功1/已导入1同Lead00034/缺姓名1。实际浏览器另存失败CSV并逐字段校验PASS（UTF-8 BOM、8列仅一错误行、中文/引号/换行及公式防护），桌面结果截图已读。没有重跑M7VISUAL001，不以临时会话拼接整链。原生Lead链接首次实点进入`/crm/setup`，当时未计详情PASS；此门槛已按下节明确授权处理，随后三详情与窄屏只读验收通过，完整移动实机仍未验。

CRM固定源码的管理员首次引导检查本站单例`FCRM Settings.setup_completed`；0会将原生记录路由引到`/crm/setup`。原生Skip setup→确认只持久该全站完成标志及浏览器本地缓存，不创建邮箱/示例/邀请，但会影响其他管理员提示，须协调授权；不要直接注入localStorage或改路由。Share usage data单独写`System Settings.enable_telemetry`，不是导入必需许可；本轮tower明确选择关闭既有遥测的实验隐私基线，不宣称此前零外发或此项阻止一切第三方请求。

### 缺失必填的正常初始化修复与最终UI证据

新站点在业务烟测前必须核验System Settings.language/time_zone有效、allow_error_traceback=0，并按明确的隐私选择配置enable_telemetry。本实验原Language/Time Zone为空，关闭遥测的原生POST真实417 MandatoryError（68524.181），未提交。固定v15.125将time_zone设为必填且read_only，原生UI不能补缺值；不能改DOM/DocField或以ignore_mandatory作为部署默认。

固定`frappe.utils.get_system_timezone`空值回退Asia/Kolkata；`now_datetime`转换本站时间后去tzinfo，新creation/modified等使用该naive时间。换时区会影响未来时间存储及默认调度，不只是显示，也不会自动迁移旧值。tower明确选择language=zh/time_zone=Asia/Kolkata，保持原有效时间语义；不直接转上海形成混合历史，不猜国家/币种。真实团队上线前须单独规划时区和历史迁移。

本次额外获批的维护初始化在本站console以正常维护身份用普通`frappe.get_doc("System Settings")`及`doc.save()`，仅设置language、time_zone、enable_telemetry；无ignore_mandatory/ignore_permissions/SQL/db.set_value。执行前快照全部字段，save后在事务内重新读取并对比，只允许这三项及modified/modified_by；任何额外差异必须rollback并停止，不能先commit再核验。实际差异仅language null→zh、time_zone null→Asia/Kolkata、enable_telemetry1→0和modified，通过后commit；新进程有效时区仍Asia/Kolkata、traceback0，密码策略1/评分2、backup3、link limit10等均不变。此为透明维护修复，不冒充原生UI设置了只读时区。回退不能盲目恢复缺失必填或重新开启遥测/堆栈；配置变更仍须协调窗口并保留审计。

原生设置重载见简体中文/Asia/Kolkata及三项官方活动审计，不变值Save未报错；没有声称又发生一次服务端设置写入。随后重载setup正常Skip setup→确认POST68524.360 **200**，fresh读取FCRM Settings.setup_completed0→1、telemetry仍0。SetupTelemetryConsent本地初值true不代表DB许可，未再点该开关而误启用。未接邮箱/生成示例/邀请/反馈。

从本轮同一导入结果逐一真实点击后，Lead tab776603404实际显示CRM-LEAD-2026-00034及姓名/企业/owner，企业tab776603407显示名称/联系人1，Contact tab776603410显示姓名及关联企业，均snapshot核对业务字段。390×844只读仿真两截图已读：页面宽390无整体横溢，两个长表局部overflow-x:auto；非手机实机或原生安装包验证。已恢复metrics/focus仿真、停本人network capture、不关用户tabs/session，并释放共享实例/UI窗口。产品逻辑自c8b870b未变，当前仅文档与新合成CSV；无create负例、M8完整团队权限及恢复演练不在完成声明内。

当前站点安全开关已由M6改1→0并独立12API负测通过。正常System Settings save曾被既有language/time_zone缺失阻断且未提交；M6后仅对该目标设置使用ignore_mandatory保存并clear-cache。不能把此例外写成通用绕过必填流程，新站点正常Save为首选；若被已有资料问题阻断，先停止并协调定点处理，不随意填造语言/时区。

### HTTP合成核验

HTTP操作核验（需要现有部署runtime，仅程序内部使用现有登录材料、不打印凭据；显式写入并保留M7合成资料）：

```sh
python3 deploy/verify_resource_import.py --runtime-dir /mnt/p/CRM/deploy \
  --prefix M7UniqueRun001 --confirm-synthetic-write
```

核验覆盖匿名/登录页、POST/CSRF、预览无业务写入（仅短期Redis receipt）、共享/确认/文件来源篡改/缺失/跨会话receipt校验、逐行错误、失败回滚无企业孤儿、重复/并发双会话、原文/来源/完整hash、显式消歧与原生对象链接。每次使用新前缀；不会删除旧验收数据。此脚本不等于浏览器视觉/真实文件控件/失败CSV下载验收，也不等于非管理员实际会话或备份恢复验证。

首轮M7窗口实测：旧镜像`2408974e...`和主私有`pre-m7-image.env`保留；with-files新备份数据库非空+公/私tar+site config四件最近生成已核对，未恢复。安装中patch manifest漏pre_model_sync节、www controller应使用下划线、本站无encryption_key及Long Text会清洗HTML均经真实检查发现并修正，未通过时未宣称完成。最终14字段只增（保留五个早期Long Text，新导入只写五个Code verbatim原文；不变更字段类型/全局过滤器），两次migrate、实际唯一索引及HTTP矩阵核验见IMPORT_APP。历史候选`sha256:36a89c9b0ad6eae3842ba4a32c7c54cfa45c6a7c135041893ba55b9f2f07e238`存在后续确认的manifest故障，不能再当当前可交付镜像；当前运行以本节上述精确c8b870b构建的c47b7cc镜像为准。兼容回退`sha256:6490855bc7f8e2a78523ac40ad3b5b024d745965ac9c2e834c3bfa9b10641fe9`保留，回退前须重验标准登录资产，不假定它自动包含后续修复；入口关闭/字段数据保留原则不变。M7HTTP001保留3企业/4联系人/6Lead，M7VISUAL001与M7STANDARDUI001保留且不盲目复跑；M6最终负测和本轮标准UI证据见上文，不把管理员合成导入通过当完整MVP。

## 官方证据

- [CRM安装stable路径](https://docs.frappe.io/crm/introduction/installation) / [v1.90.0发布](https://github.com/frappe/crm/releases/tag/v1.90.0)
- [Docker拓扑参考](https://github.com/frappe/frappe_docker/commit/61d35da827ebc04d01b64c9e78385597ccebc9d8)
- [Docker Library MariaDB](https://github.com/docker-library/official-images/blob/master/library/mariadb) / [Redis](https://github.com/docker-library/official-images/blob/master/library/redis)
- [Amazon ECR Docker Official Images](https://gallery.ecr.aws/docker)
- [CRM许可证AGPL-3.0](https://github.com/frappe/crm/blob/v1.90.0/LICENSE)
