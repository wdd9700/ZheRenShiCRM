# 远端合成部署真实执行记录（C010600）

**状态：已在 `dev@8.133.190.46` 上完成独立合成试用部署的真实建站、启动、扩展前备份、双扩展安装、两次迁移与 G1 观测；站点只监听 `127.0.0.1:8088`，使用全新合成的凭据与数据。未做 Windows 客户端安装、真实浏览器登录、权限矩阵、PWA、恢复演练，也未解除 M8/M9 门禁。**

本文件记录两轮真实执行：第一轮在 M13 精确 `240b9a8…` 的镜像身份门禁处失败并保留现场；M13 修复合约并独审 clean 后，第二轮按 `92f9de6…` 的工具更新包恢复，从 `check` 继续到 G1。文中所有结论都来自本轮实际命令输出；未执行项在 §13 明列，观测限制在 §14。

## 1. 授权与范围

用户明确要求"服务端部署上线，客户端安装，我在 win 下试试"，并授权在该服务器使用 sudo 安装 Docker/Compose 用于调试、部署与实际测试。M14 已完成安装并合并；M13 在 `240b9a8` clean/hold、`92f9de6` 工具更新 revision clean/hold（hold 只保留 M9 真实依赖与生产门禁）。

| 允许并实际执行 | 禁止并未执行 |
|---|---|
| 只读现场复核、精确源码/镜像交付与两端摘要核验 | 重建镜像、改候选源码、改 `deploy/remote/*` 已审内容 |
| 按已审脚本以 `dev` 更新整组工具、保留旧工具与 `.runtime`/`.env`/`apps` | 重新 `init-env`、重新 `load-image`、覆盖或重建凭据 |
| 精确旧 index 锁 → config 锁的原子迁移（保留旧锁） | 重新生成镜像、切换 image store、加 `docker` 组、`systemctl enable` |
| 建合成站点、启动 9 服务栈、扩展前备份、装两个扩展、双迁移、G1 观测 | 导入真实客户资料、清库/重置、`down -v`/`prune`/`uninstall-app`、删任何既有资源 |
| 只读 HTTP ping 与路由观测 | Windows GUI 操作、公网暴露、改防火墙/安全区/sshd/swap |

## 2. 连接与主机身份

全程 Git Bash `/usr/bin/ssh`，固定 `-o UserKnownHostsFile=…/m10-known_hosts -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o BatchMode=yes`；私钥只作 `-i` 参数，未读取/打印/复制正文；本文件不含任何密码、私钥或 `.env` 值。

```
$ ssh-keygen -lf …/m10-known_hosts
256 SHA256:JHFV75F2oc1tYqjd4viv130aknkd7fOwtKEpmGtgy80 8.133.190.46 (ED25519)
```

与 M10/M14 记录逐字符一致，且严格主机校验下连接成功。**仍是 TOFU 记录，未做带外认证**。每次连接仍打印无 PQ KEX 警告（服务器 sshd 较旧），未修改。

主机：`iZuf6htx2n3srizz88227cZ`，`Linux 5.10.134-19.8.al8.x86_64`，`alinux 3`，2 vCPU，MemTotal 1870 MiB，无 swap，`/dev/vda3` 40G；`dev` 在 `wheel`、**不在 docker 组**；Docker 26.1.3（`active` / `disabled`），Compose v2.27.0。

## 3. 第一轮（`240b9a8`）：交付、预检、加载与门禁失败

### 3.1 现场只读复核（通过）

0 容器、0 卷，网络仅 `bridge/host/none`，`~/crm-trial` 不存在，8088 未监听，`/etc/docker` 无 `daemon.json`；`sudo -n true` 成功。注册表探测：`public.ecr.aws` 401、`ghcr.io` 401（可达），`registry-1.docker.io` 超时（401 只证明端点响应，随后真实 pull 另行验证，见 §7.1）。

### 3.2 交付准备与独立核证（通过）

复用 wt-9 已核证 context，M13 文件由 `git archive 240b9a8` 取得。**独立核证**（不只依赖随包 manifest）：逐条用 `git show <commit>:<path>` 取精确 blob，与交付文件和 `SOURCE_SHA256SUMS` 三方比对，**53/53 相等**（`faa5f03…` resource_import、`0e5fed7…` team_access、`a1ce4ca…` deploy；`deploy/Dockerfile*` 经 CRLF→LF 规范化后等值）。`source-manifest.json` LF 摘要 `e4877bea…4df5b374`。

本地导出与传输摘要：

```
33caf5473b79b46b7c1b1fb25deef801cbabf56779d04c2853f7e9a234e159a4  crm-trial-c010400-source-and-tools.tar
a5588c193efce06e6e53591a3ce38046908c06c30c6cf097ba320387c545b7db  crm-c010400-image.tar
```

`docker save` 真实退出 0、tar 完整生成（1,539,445,760 字节）后才计算摘要；`scp` 退出 0（2m14s），远端 `sha256sum -c` 两件 OK（传输前后摘要一致）。镜像 ID 从未当作 tar 摘要。

### 3.3 预检（PREFLIGHT READY）

从同一已核验 tar 只提取 `preflight.sh` + `docker.sh` 到 `/tmp/crm-trial-preflight.8ZF2Wh`，`CRM_TRIAL_DOCKER_SUDO=1` 下 exit 0：x86_64、alinux 3、MemTotal 1915884KiB / available 1575060KiB、swap 0、home 与 `/var/lib/docker` 各余约 30GiB、四卷/网络/create-site 容器均不存在、无本项目容器、8088 空闲；预检前后目标目录均不存在。

### 3.4 解包、源码校验、加载与新凭据

`mkdir ~/crm-trial` → 解包 → `verify-source` PASS（53/53）→ `load-image` 退出 0（2m5s）→ `init-env` 只执行一次（`.runtime` 700，`.env`/`image.env` 600，值未打印）。

### 3.5 门禁失败：镜像 ID 命名空间不匹配

```
$ sh deploy/remote/trial.sh check
Error response from daemon: No such image: sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705
ERROR: exact candidate image is not loaded      (exit 1)
```

加载结果是 `sha256:129b03571ac973784c7a3dab851ec31496db6b689bbbd8935337b068dea81c07`。根因由 M9 构建日志直接证明：

```
#13 exporting config sha256:129b03571ac973784c7a3dab851ec31496db6b689bbbd8935337b068dea81c07
#13 exporting manifest sha256:6014c9df39452ce0cf0e6834822d7d1de89b814ef11f1d6e78bb1ea5c1f50a60
#13 exporting attestation manifest sha256:b2527381d33e7178e1feb74a100c0ee57c5eeedca23839b6d9d273a9a7be7cb1
#13 exporting manifest list sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705
```

`cae67cc3…` 是 buildx 的 manifest list / OCI index 摘要；M9 构建机是 containerd image store（`.Id` 报 index），目标是经典 overlay2（`.Id` = config 摘要），所以该门禁在经典 store 上不可能通过。交付物内容等价已独立核验：tar 是合法 OCI layout、**26 个 blob 逐个自校验一致**、`manifest.json.Config=129b0357…`、`index.json` digest=`cae67cc3…`、24 层 diff_ids 与三 revision label 和远端加载镜像逐项相同；尺寸差异属口径（压缩 1,539,417,571 vs 未压缩 4,187,705,330），不能当身份判据。停止后 0 容器、0 卷、无站点，现场保留。

## 4. M13 修复与第二轮恢复（`92f9de6`）

### 4.1 恢复前核对（与停点一致）

指纹不变；主机/Docker 状态不变；0 容器 0 卷、仅默认网络；镜像仍 `129b03571ac9`；`~/crm-trial` 53 文件、manifest `e4877bea…`；旧工具（trial.sh 10454B、release.env 572B、compose.yml 5670B 等）；`.runtime` 700，`.env` 600/188B、`image.env` 600/82B=`cae67`；无任何 stage marker；`~/c010600-delivery` 两件 `sha256 -c` OK；仅 22 端口；27G 余。无意外变化。

### 4.2 工具更新包（独立制作与复核）

`git -C wt-13 archive 92f9de637007a4c9a25853375958f53bdb4e51a0` 取 13 文件白名单（`git status --porcelain` 为空，无未提交文件）：

```
f44c131d5d0c1f93b9cb3884f5954e3f6aefa7fbb3e9abdbac994cb0652ef461  crm-c010400-tools-update.tar
```

与 M13 作者和独审**各自复算**的值逐字符一致。远端新目录 `~/c010600-tools-update`，`sha256sum -c` OK，解包到 `/tmp/c010400-update-staging.is7bB0`。

`apply-tools-update.sh`（以 `dev` 运行，不带整脚本 sudo，不调用 Docker）：

```
PASS: exact tool group updated; old tools retained at /home/dev/crm-trial/deploy/remote.pre-c010400-update; runtime, apps and Docker resources untouched
```

它先独立核验 tar SHA、13 项白名单、成员类型/路径，再要求既有工具与 `240b9a8` 的 10 项旧摘要全一致，把旧工具复制到 `deploy/remote.pre-c010400-update`，逐文件更新并整组比对。**runtime 与 apps 未变**（只记录一致性、不打印秘密或摘要）：`.env` 600 dev:dev 188B、inode 130932、mtime 1793461009 前后相同；`apps` 51 文件与两个哨兵 `hooks.py` 摘要前后相同。

### 4.3 锁迁移与真实 `check`（通过）

```
$ sh deploy/remote/trial.sh migrate-image-lock-to-config --confirm-classic-image-lock-migration
PASS: exact index lock migrated to config atomically; previous lock and .env retained unchanged

600 dev:dev 188 deploy/remote/.runtime/.env
600 dev:dev  82 deploy/remote/.runtime/image.env                          -> CRM_IMAGE=sha256:129b0357…
600 dev:dev  82 deploy/remote/.runtime/image.env.pre-c010400-config       -> CRM_IMAGE=sha256:cae67cc3…

$ sh deploy/remote/trial.sh check
PASS: Compose and classic-config image lock, linux/amd64, three labels and all RootFS diff_ids; runtime health not yet proven
```

迁移只接受精确旧 index 锁，先验证 config 的 ID/平台/labels/完整 24 层 RootFS，再要求旧锁为 0600 非符号链接，原子替换并保留旧锁；`.env`、apps、站点、容器、卷均未被触碰。`check` 通过的是**身份与渲染**，不是应用健康。

## 5. 建站与启动

```
$ sh deploy/remote/trial.sh create-site --confirm-synthetic-only      -> PASS (1m38s)
$ sh deploy/remote/trial.sh up                                        -> PASS (9.4s, exit 0)
```

- `create-site` 只用 `bench new-site --install-app crm` 安装 CRM，并把合成声明、`resource_import_disabled=1`、`server_script_enabled=0`、`mute_emails=1` 写入新站配置；未自动安装扩展。
- `up` 使用 `compose up -d --wait`，9 个长驻服务全部 Running/Healthy，DB healthy；frontend 仅 `127.0.0.1:8088->8080`。
- 首次真实拉取 `public.ecr.aws` 固定 digest 的 mariadb 与 redis 成功（未用浮动 tag）。**Docker Hub 不可达不影响该栈**，因为 db/redis 固定走 `public.ecr.aws`；这是本轮栈的实际依赖路径，不代表其他镜像也可靠。

## 6. 扩展前备份、扩展安装、双迁移与版本

顺序由 `bench.log` 时间戳独立佐证，不只是脚本返回码：

```
16:27:37  bench --site crm.localhost backup --with-files
16:27:44  bench --site crm.localhost install-app resource_import
16:27:53  bench --site crm.localhost install-app team_access
16:28:02  bench --site crm.localhost migrate
16:28:10  bench --site crm.localhost migrate
16:28:17  bench --site crm.localhost clear-cache
```

- **扩展前备份**（`backup`，exit 0）：四件齐 —— site config 208B、database 282KiB、public files 10KiB、private files 10KiB，stem `20261031_215738-crm_localhost`；只做读取完整性检查，**未做恢复演练**，因此不称恢复通过。
- **install-extensions**（`--confirm-synthetic-only`，exit 0）：`resource_import` 后 `team_access`，两者均返回零。
- **migrate**（exit 0）：两次完整 `bench migrate` 加一次 `clear-cache`。
- **versions**：

```
crm 1.90.0
frappe 15.125.0
resource_import 0.1.0
team_access 0.1.0
frappe.get_installed_apps -> ["frappe", "crm", "resource_import", "team_access"]
```

## 7. G1 实测结果

### 7.1 HTTP 与路由

```
GET /api/method/ping   Host: crm.localhost      -> {"message": "pong"}  HTTP 200  (0.34s)
GET /api/method/ping   无 Host 覆盖              -> pong               HTTP 200
GET /api/method/ping   Host: 127.0.0.1:8088     -> pong               HTTP 200
GET /api/method/ping   Host: 127.0.0.1:18088    -> pong               HTTP 200
GET /login             无 Host 覆盖              -> HTTP 200 text/html, title "Login"
GET /login             Host: crm.localhost      -> HTTP 200 text/html
```

路由事实（非秘密字段）：nginx `frappe.conf` **只有一个** server 块，`server_name crm.localhost;`，因此对未匹配 Host 的请求充当默认 server；`sites/apps.txt` = `crm / frappe / resource_import / team_access`；`sites/` 下只有 `crm.localhost`。`common_site_config.json`：`db_host=db`、`db_port=3306`、`redis_cache=redis://redis-cache:6379`、`redis_queue=redis://redis-queue:6379`、`redis_socketio=redis://redis-queue:6379`、`socketio_port=9000`。`site_config.json` 非秘密项：`db_name=_c8b3e5206096f0bd`、`db_type=mariadb`、`mute_emails=1`、`resource_import_disabled=1`、`server_script_enabled=0`、`team_access_synthetic_only=1`（隐藏字段只有 `db_password`，未打印）。

限定表述：**单站点 + 单 nginx server 块**下 127.0.0.1 访问可解析到该站点；多站点时行为会变，不承诺永久如此。

### 7.2 服务、端口与容器计数

`docker ps -a` 共 **11 个容器对象 = 9 个运行中长驻服务 + 2 个一次性容器（Exited 0）**：

| 服务 | 状态 |
|---|---|
| backend | Up |
| db | Up (healthy) |
| frontend | Up（仅 `127.0.0.1:8088->8080`） |
| queue-short | Up |
| queue-long | Up |
| scheduler | Up |
| websocket | Up |
| redis-cache | Up（纯缓存，无具名持久卷） |
| redis-queue | Up（`--appendonly yes`，挂 `crm_trial_c010400_redis`） |
| configurator | Exited (0)（一次性初始化） |
| create-site | Exited (0)（一次性建站） |

两个 Redis 是**独立服务、独立容器**，不是同一实例的两种视图。监听端口只有 `0.0.0.0:22` 与 `127.0.0.1:8088`（外加 `[::]:22`），**未暴露公网 8088**。

### 7.3 重启、OOM 与资源

全部 11 个容器的 `RestartCount=0`、`State.OOMKilled=false`。一次 `docker stats` 快照（`--no-stream`）：

```
backend 185.7MiB / db 139.4MiB / scheduler 60.7MiB / queue-long 45.3MiB
queue-short 36.2MiB / websocket 22.7MiB / redis-cache 3.3MiB / redis-queue 2.4MiB
frontend 3.1MiB        （合计约 499MiB）
host: used 862MiB, available 1008MiB, buff/cache 365MiB, swap 0
```

## 8. 短期资源观察

第一次取样循环（10 点、每点含逐容器 `docker stats --no-stream`）在本机 1.8 GiB 负载下每点过慢、超出预期时长，被**主动中止**（只终止本地采样会话，未改远端任何状态，采样期间站点持续可 ping）。随后改用合并 `docker inspect` 的轻量采样重跑，结果如下。

### 8.1 采样（8 点，每 20 秒一次，约 2.5 分钟）

| # | 时间 | host used | host available | 运行容器 | 累计 restart | OOM | ping |
|---|---|---|---|---|---|---|---|
| 1 | 00:37:12 | 853 MiB | 1017 MiB | 9 | 0 | 0 | 200 |
| 2 | 00:37:33 | 855 MiB | 1015 MiB | 9 | 0 | 0 | 200 |
| 3 | 00:37:53 | 854 MiB | 1016 MiB | 9 | 0 | 0 | 200 |
| 4 | 00:38:13 | 855 MiB | 1015 MiB | 9 | 0 | 0 | 200 |
| 5 | 00:38:34 | 854 MiB | 1016 MiB | 9 | 0 | 0 | 200 |
| 6 | 00:38:54 | 856 MiB | 1014 MiB | 9 | 0 | 0 | 200 |
| 7 | 00:39:14 | 855 MiB | 1015 MiB | 9 | 0 | 0 | 200 |
| 8 | 00:39:34 | 854 MiB | 1016 MiB | 9 | 0 | 0 | 200 |

`dmesg` 全量扫描 `out of memory|killed process` 命中 **0** 行。采样期间无自动扩容、无加 swap、未停任何其他服务、未降低权限。

### 8.2 观察结论与限制

- 2.5 分钟窗口内 host 内存稳定在 853–856 MiB used / 1014–1017 MiB available，运行容器恒为 9，累计 restart 恒 0，OOM 恒 0，ping 恒 200；完整 `docker stats` 快照（§7.3）显示容器合计约 499 MiB。
- 这只是**短窗口的当前可用性证据**，不是长期稳定性或容量保证：1.8 GiB / 无 swap 余量仍薄，`bench migrate`、备份、索引重建、真实业务负载等峰值未在本窗口重复压测；观察时长和采样密度都远不足以称为"稳定运行"。

## 9. 保留的资源清单

| 资源 | 状态 |
|---|---|
| `~/crm-trial` | 源码树 + 工具（新 13 件）+ 旧工具备份 `deploy/remote.pre-c010400-update` + `.runtime` |
| `.runtime/` | 700；`.env` 600（凭据，未打印）、`image.env` 600（config 锁）、`image.env.pre-c010400-config` 600（旧 index 锁）、marker `site-created` / `extensions-installed` / `migrated-twice` 均 600 |
| `~/c010600-delivery` | 两 tar + `DELIVERY_SHA256SUMS`（`sha256 -c` OK） |
| `~/c010600-tools-update` | 更新 tar + 原始 `.sha256` |
| `/tmp/crm-trial-preflight.8ZF2Wh`、`/tmp/c010400-update-staging.is7bB0` | 预检/更新临时目录（仅脚本副本） |
| 镜像 | `129b0357…`（4.19GB，untagged）+ 拉取的 mariadb/redis 固定 digest |
| 命名卷 | `crm_trial_c010400_{db,redis,sites,logs}`，均创建于 2026-11-01 00:26:01 |
| 匿名卷 | `da155ae8…`，label `com.docker.volume.anonymous`，归属 `redis-cache-1`（redis 镜像声明 `VOLUME /data`，compose 未给该服务挂具名卷），保留未删 |
| 备份文件 | 站点卷内 `private/backups/20261031_215738-crm_localhost` 四件 |
| 磁盘 | `/` 已用 12G，可用 26G |

## 10. 未执行项（不得视为通过）

- **G2**：未做 System Settings 基线（Show Full Error / telemetry）、未做真实浏览器表单登录、未核验登录页资产 hash/MIME。
- **import 仍禁用**：`resource_import_disabled=1` 实测有效；未执行 `enable-import`。
- **G3**：未创建合成双用户、未做任何权限矩阵；M8 完整矩阵与生产门禁未推进。
- **G4/G5**：Windows SSH 隧道未建立、Edge PWA 未安装（未操作 GUI）。
- **G6**：未执行 `stop`，未做同版本恢复演练；备份只验证可读。
- **容量**：只做了短窗口观测，见 §8.2。

## 11. 凭据与后续接入

- 凭据只在远端：`~/crm-trial/deploy/remote/.runtime/.env`（600，含 DB 与 Administrator 合成口令）。本轮未打印、未回传、未复制到本地或 Git。安全获取方式：以 `dev` 登录后本地读取；不要经命令行参数、日志或聊天传递；`init-env` 拒绝覆盖，禁止重建。
- Windows 接入前提（尚未执行，未声称可用）：SSH 隧道到 `127.0.0.1:18088`，专用 known_hosts + `StrictHostKeyChecking=yes` + `IdentitiesOnly=yes`，仅回环、不开公网；按 §7.1，单站点下 127.0.0.1 访问可直接解析到该站点。

## 12. 只读复核清单

以下命令全部为查询，不创建、不启动、不改配置（`<KEY>` 只作 `-i` 参数）：

```sh
ssh -i <KEY> -o UserKnownHostsFile=<m10-known_hosts> \
  -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o BatchMode=yes dev@8.133.190.46 'sh -s' <<'EOS'
cd "$HOME/crm-trial" && sha256sum -c deploy/remote/SOURCE_SHA256SUMS
sha256sum source-manifest.json
stat -c '%a %U:%G %s %n' deploy/remote/.runtime deploy/remote/.runtime/.env \
  deploy/remote/.runtime/image.env deploy/remote/.runtime/image.env.pre-c010400-config
cat deploy/remote/.runtime/image.env
sudo -n docker ps -a --format '{{.Names}}|{{.Label "com.docker.compose.service"}}|{{.Status}}'
sudo -n docker volume ls
sudo -n docker image inspect sha256:129b03571ac973784c7a3dab851ec31496db6b689bbbd8935337b068dea81c07 \
  --format '{{json .Config.Labels}}'
curl -sS -H 'Host: crm.localhost' http://127.0.0.1:8088/api/method/ping
ss -ltn
EOS
```

`.env` 只做 `stat`，不要 cat。

## 13. 证据摘要

| 阶段 | 命令（摘要） | 结果 |
|---|---|---|
| 身份 | `ssh-keygen -lf m10-known_hosts` | `SHA256:JHFV75F2…y80`，TOFU |
| 交付核证 | `git show <commit>:<path>` ×53 + `SOURCE_SHA256SUMS` | 53/53 相等；manifest `e4877bea…` |
| 导出/传输 | `docker save`；`scp`；两端 `sha256sum -c` | tar 1,539,445,760B `a5588c19…`；传输退出 0 |
| 预检 | 提取 `preflight.sh`+`docker.sh` 到 `/tmp`；`CRM_TRIAL_DOCKER_SUDO=1 sh …` | PREFLIGHT READY |
| 源码 | `trial.sh verify-source` | 53 文件 PASS |
| 加载 | `trial.sh load-image …` | 退出 0，ID `129b0357…` |
| 第一轮门禁 | `trial.sh check` | **失败**：`No such image: sha256:cae67…` |
| 工具更新 | `git archive 92f9de6` 13 文件；`apply-tools-update.sh` | tar `f44c131d…ef461`；整组 PASS；runtime/apps 未变 |
| 锁迁移 | `migrate-image-lock-to-config` | PASS，原子替换 + 旧锁保留 |
| 第二轮门禁 | `trial.sh check` | PASS（Compose、锁、平台、三 label、24 层） |
| 建站/启动 | `create-site`；`up` | 均 PASS |
| 备份/扩展/迁移 | `backup`；`install-extensions`；`migrate`；`versions` | 均 exit 0；四 app 与固定版本一致 |
| G1 | `curl ping`；`docker ps -a`；`docker inspect`；`docker stats` | pong 200；9 运行 + 2 Exited(0)；restart 0 / OOM false |

**结论：本轮完成了独立合成试用的真实部署——工具更新、锁迁移、身份门禁、建站、启动、扩展前备份、双扩展安装、两次迁移与 G1 观测均真实通过。未执行 Windows 客户端、真实登录、权限矩阵、PWA 与恢复演练，服务端仍只监听回环，M8/M9 门禁未推进。**
