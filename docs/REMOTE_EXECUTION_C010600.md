# 远端合成部署真实执行记录（C010600）

**最新状态（C010800，2026-11-03）：远端已按已审工具完成先备份后兼容镜像更新，健康、安全配置与五件既有业务记录保留；正常设置、上海时区、管理员导入、普通 Sales User 实际创建与有限多会话权限深验通过。此前创建 500 已复验解除；不等于完整 M8 安全矩阵、生产放行或带附件共享功能完成。详见 §14。**

§1–13 是 C010600 部署时点的历史记录，包含当时“未执行”状态，不代表后续任务没有完成。Windows 原生浏览器与安装入口由 M12 独立验收；恢复门禁由 M9 单独记录。站点始终只监听 `127.0.0.1:8088`，仅经 SSH 回环隧道接入。

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

- C010600 初始化材料位于远端 `~/crm-trial/deploy/remote/.runtime/.env`（600）。**其中旧 `ADMIN_PASSWORD` 已在 C010700 失效，不要读取它尝试登录；当前口令由用户掌握，权威见 [TRIAL_ACCOUNT_C010700.md](TRIAL_ACCOUNT_C010700.md)。** 不同步该文件、不重 `init-env`、不打印或回传 DB 秘密。验收脚本交互读取管理员口令，仅经 SSH stdin 传入，cookie 与普通用户随机口令仅留进程内存。内部敏感操作转录不属于公开交付材料。
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

**C010600 当轮结论：独立合成试用部署与 G1 通过；当轮未执行的后续验收不得据此视为通过。最新增量如下。**

## 14. C010800 可用性与权限增量验收（2026-11-02）

### 14.1 健康、安全设置与时间

- 严格主机校验 SSH 复核：9 个长驻服务 Up 46h，DB healthy，另两一次性容器 Exited(0)；四 app 版本仍为 §6 所列。ping 200/pong；仅 SSH 与 `127.0.0.1:8088` 监听；内存 available 945 MiB、无 swap。本轮没有重部署、重初始化、迁移、删除容器/卷/备份或改网络策略。
- 原 System Settings：`language/time_zone` 空、`allow_error_traceback=1`、`enable_telemetry=1`。管理员真实登录、获取正常 Desk CSRF 后，经受支持的 `frappe.client.get/save` 完整单例正常校验保存；没有 `ignore_mandatory`、`ignore_permissions`、SQL、DOM 或全局权限绕过。
- 首轮补必填 `zh/Asia/Kolkata` 并关闭 traceback/telemetry；复核固定运行源码 `now_datetime()` 先由 UTC 转系统时区再去掉 tzinfo，空系统时区原有效默认 Kolkata。随后确认 Lead/Deal/Contact/Organization/Task/Note 六类业务对象全为空，按中国团队语义再正常保存为 **`language=zh`、`time_zone=Asia/Shanghai`、`allow_error_traceback=0`、`enable_telemetry=0`**。不批量重写历史；旧系统审计 naive 时间仍可能属 Kolkata，不应按上海重新解释。
- fresh API 读取上述四值匹配，密码策略仍启用、minimum score 仍 2。匿名导入 API 403 且无 `exc/exception`，认证后管理员身份与正常业务 API 可用。Guest 调 `get_logged_user` 本版返回 403，不将其误判成服务故障。关闭 telemetry 不保证阻断所有第三方网络行为。
- 只过滤非秘密 site config 复核：`mute_emails` 严格整数 1、`server_script_enabled=0`、`team_access_synthetic_only` 严格整数 1；未读取/打印 DB 或旧初始化口令。
- 上海时间实际验证：管理员通过正常 API 创建合成跟进 Task `2`，`creation=2026-11-02 22:49:38.636849`，与同刻 UTC+8 差小于 120 秒；`due_date=2026-11-03 22:49:38` 创建后重读完全一致。Task `1` 为先前脚本兼容性断言失败留下的同类合成记录，保留不删。此为 API 时间往返，不冒充浏览器时间控件展示验收。

### 14.2 合成导入与入口

安全基线通过后，执行既有受控命令 `CRM_TRIAL_DOCKER_SUDO=1 sh deploy/remote/trial.sh enable-import --confirm-synthetic-only`，只将 `resource_import_disabled` 设 0 并清本站缓存，返回 PASS。

同一真实管理员 HTTP/CSRF 会话使用 `C010800-REMOTE-20261102.csv`，邮箱 `c010800@example.invalid`，无真实资料、无邮件：

| 验收 | 实际结果 |
|---|---|
| 三行预览 | 正常行、文件内重复、缺姓名错误反馈可辨认 |
| 明确共享确认 + 二次导入确认 | 成功 1 / 已导入 1 / 失败 1 |
| 同 receipt 重复确认 | 已导入 2 / 失败 1，无第二条 Lead |
| 业务关联详情 | Lead `CRM-LEAD-2026-00001`、`C010800-REMOTE-20261102合成企业`、同前缀 Contact 三类详情均正常查询；需求原文一致 |

记录全部保留。管理员成功只证明该受控入口可用，不证明普通销售私域安全。Windows 经既有 SSH 隧道：`http://127.0.0.1:18088/login` 正常登录，CRM `/crm`，导入 `/resource-import`（只限管理员/System Manager）；不开放服务器公网端口。Windows 原生 Edge 登录/安装应用/独立入口重启为 M12 独立结果，本节 API 验收不替代其浏览器证据。

### 14.3 普通用户初测失败（保留历史，已由 §14.4 实测解除）

两轮各创建两名 `C010800-TEAM-<唯一时间>-a/b@example.invalid` 合成账号，只授予 Sales User、关闭欢迎邮件，随机强口令仅进程内存，分别真实登录并核验身份成功；会话结束后注销。未提升角色、未管理员代建替代普通用户、未关闭权限扩展。

**失败并停止：** A 标准 `frappe.client.insert` 创建自己拥有的 CRM Lead，字段仅 `doctype/first_name/status=New/lead_owner=A`，返回 HTTP 500、`exc_type=TypeError`，未提交 Lead。定点诊断以同 A 的正常 ORM insert（不忽略权限）在 finally rollback 事务内复现，根因：

`CRMLead.after_insert → assign_agent → ToDo.add_assign_comment → team_access.events.validate:44 → permissions.can_contribute:44 → can_reference:35 → frappe.has_permission(..., raise_exception=False)`。

实际 Frappe 15.125.0 外层签名是 `has_permission(..., throw=False, ...)`，不接受 `raise_exception`；该关键字仅属于内部 `frappe.permissions.has_permission`。运行 `frappe/__init__.py` SHA256 `4538c6ac2da144ef1c0460443b05ef1028a04236fa27307e34b8d5e936a614af`。已提交 high finding 给 tower，由所属 worker 修复和独审，M17 不在 scope 外热改代码。

**该停点未执行的后续权限流程，在兼容修复部署后由下节重新使用普通用户真实会话验收；未将管理员成功补算为普通用户成功。** M8 完整安全矩阵与生产门禁仍保留。

### 14.4 兼容补丁受控更新窗口

工具精确来源为 M13 已审 `eaffe942b48dd88b5978a2954e64b56d2847c493`，M8 仅三处 API 兼容修复 `9c0c8f50e159fd58dc1a647b1884656377ef8a04` 获有限 clean/hold，不等于整体权限放行。工具由该 Git commit `git archive` 生成（干净 wt13），不复制未提交工作树；工具 tar SHA256 `3b8d5cf40d5d3b6651b5401e9cc65cd37fa5bf5ce5aff54f75f2771bfae80e56`。独立 staging：`/home/dev/c1102-reviewed-update-eaffe942`，旧 `~/crm-trial` 工具/runtime/旧包保留。

M9 交付 tar `crm-m9-compat-c1102-image.tar` 1,539,446,272 字节，SHA256 `e00a4c2c6573588abec8d28ff8b33dab0f9d7ef5dcffe1250ee1c18b1601ebba`；release.env SHA256 `1770decfda6d3d3619fdaacae21423386a8617779ca02714adeb7784b3ff2fa9`，24 层清单 SHA256 `defbc996a7829b70c0f00e0e335ddc3db7b5704dd399fc064fe542826614ec05`。三件及工具 tar 本地与严格 SCP 后远端摘要逐项相同；两端流式完整链校验通过：index `34fc2237…` → amd64 manifest `22c02958…` → config `fb00dd79…` 与每个解压 diff_id。

执行前磁盘余 26 GiB、available 907 MiB、无 swap；五件业务文档 `preserve` 摘要与 §14.2 后记录完全一致。显式 `CRM_TRIAL_RUNTIME_DIR=/home/dev/crm-trial/deploy/remote/.runtime`、`CRM_TRIAL_DOCKER_SUDO=1`，调用独立 staging 的 `update-site-image <release绝对路径> <tar绝对路径> --confirm-site-image-update`，真实 exit 0（184 秒）。本次备份 `20261103_000232-crm_localhost` 四件完整可读后才 load；六长驻应用全为新 config `sha256:fb00dd79167160c4e00d9678ff7df3f59c8e86a932e029384112145fc8a134ae`，configurator 同 config、Exited(0)，原 create-site 历史容器保留旧镜像。脚本核 DB/双 Redis IDs、`.env`、site_config 不变，保留旧锁/镜像/工具/包/备份，未重 init、migrate、改网或删资源。

更新后同 staging + 原 runtime 的 `maintenance-status=ready`、`check` 身份/labels/24层 PASS；独立再次核 DB/双 Redis IDs 不变、四命名卷创建时间仍为 11-01、六 app 仅挂原 sites/logs 卷且 restart=0/OOM=false。`preserve` 五件完整文档 SHA 与更新前逐项全等；深验与重复导入后再次比对仍全等。最终 available 886 MiB、磁盘余 25 GiB、无 swap，仅 SSH/回环8088。此短期健康不是长期容量保证。

**远端真实普通用户验收：** R2 最终唯一组 `TEST-C010800-TEAM-20261102163350`，A/B 仅 Sales User，标准密码登录、CRM/Desk CSRF与身份；所有业务由普通账号自己创建，管理员仅建用户及核验。修订后 `team` 真实远端 exit 0（约25秒）；结果如下（HTTP/API 会话，不冒充双用户浏览器 UI）：

R1 独审指出 `d47b0df` 的证据缺口：旧组 `TEST-C010800-TEAM-20261102161118` 的 fresh B 只测列表等渠道，详情拒绝函数固定使用旧 B，未实际覆盖 fresh B 直接详情请求；A Task/B Lead 也未显式断言响应及重读的 owner。旧版文案/PASS 对此过述，不能作为这些断言的通过证据。R2 将拒绝函数参数化，每类撤权后重新登录 B，分别对旧/新 B 直接调用标准 `frappe.client.get/save`；补齐 Task/Lead owner 双断言，不改权限实现、不部署。原始 stdout 由执行管道直接保存，不是手工转录：`P:/CRM/.tower/worktrees/wt-17/deploy/.runtime/m17-r2-team.stdout.log`；本轮只读保留复核为同目录 `m17-r2-preserve.stdout.log`。两文件均 ignored、不入 Git，仅含输出；不要把含敏感输入的命令/会话转录当作可分享证据。

| 场景 | 实测 |
|---|---|
| A/B 正常能力 | A 自建 Lead/本人 Note/Task；B 自建 Lead/本人 Note；A Task `7` 与 B Lead `CRM-LEAD-2026-00009` 均显式断言创建响应及本人重读 owner 等于对应账号；对方私文403 |
| 私父及共享/撤回 | A 私父对B详情/列表/正常文本筛选/link选择/CRM列表/CSV不可见；显式父read-only共享后详情200，撤回后旧/新B同入口再次不可见，直接详情及写各403、owner完整文档未变 |
| 文本 Note/Task | Private对B拒绝；Shared对父读者B可读但写403；显式collaborator后B合法写200、A读回一致；撤回后旧B/撤权后新登录B各自直接详情403、写403，每次owner完整doc与请求前全等 |
| 入口一致性 | Note/Task本人正向与B私有/共享/撤回的标准详情、列表、文本筛选、关联选择、父活动时间线、标准CSV导出一致；普通/匿名导入API403且无堆栈 |
| 私附件 | A正常创建私File并读取字节200；B/匿名403；明确collaborator后B字节200；撤回后旧B/撤权后新登录B/匿名403，A仍200且字节相等 |
| 商机关联 | A正常Lead转换生成企业/Contact/Deal，三类关联详情200；Deal私有B403、显式read-only共享B200/写403；撤回后旧B/撤权后新登录B各自直接详情403、写403，每次owner完整doc未变 |
| 时区 | A Task creation为`2026-11-03 00:33:55.507546`，与UTC+8相符；due_date=`2026-11-04 00:33:55`读回全等 |
| 管理员导入回归（前轮） | 更新后再次preview/apply旧合成来源，重复2/错误1、关联详情原文正常；R2不重复导入，改用只读preserve复核 |

R2 的四类对象 × 旧/新 B 共八次直接详情与八次拒绝写均为 HTTP403，八次拒绝写前后 owner 读取的完整文档逐项全等。本组保留 A Lead `CRM-LEAD-2026-00008`、文本 Note `kje4nhtjnr`、Task `7`、Deal `CRM-DEAL-2026-00003`、B Lead `CRM-LEAD-2026-00009` 等；前组与失败现场同样保留，未批量清理。所有本工具会话最终注销，普通口令不落盘、不输出。

R2 随后 `preserve` exit 0：ping、安全设置断言通过，六长驻 app 仍为 `fb00dd791671`，DB healthy、监听仍仅 SSH 与回环8088；五件既有完整文档摘要与部署前基线逐项比较一致：Lead00001 `7d5b860a…550b8d`、Organization `56f48d86…9abd4`、Contact `451095ca…acac0`、Task1 `19d08947…5eb6`、Task2 `8d3024f7…eea22`。`preserve` 本身只生成摘要，比较是此次对原始输出与既有基线的逐项核对，不把其 PASS 行当自动比较。

**明确产品限制与负例：** 当前策略禁止把带私附件 Note/Task 直接改成 Shared。第一修后组在此返回417后停止；最后两组将私附件与纯文本共享分开，同时显式复测该转换返回417，Note完整字段/Private可见性、File完整字段/私有状态均未变，B仍不可读。没有删除附件、转公共文件或改安全字段绕过。用户若要共享带附件内容，当前不支持该直接转换；不能将文本共享成功说成完整附件共享功能。

**仍未覆盖/不放行：** M8 全部 legacy/历史 DocShare、实时 socket/通知及全部旁路矩阵；双普通用户浏览器UI、普通用户导出全部业务字段和大批量导出、手机实机；远端本轮备份真实恢复、长期容量。当前导出只验证标准CSV入口的授权记录ID集合，不等于全字段导出审计。Org/Contact属于已明确共享的业务资料，不能当私域对象。M12独立浏览器/安装证据和M9隔离恢复证据各自保留，不拼接成远端完整安全验收。未发现本次覆盖场景泄露，不声称证明全站无泄露。

### 14.5 可复用脚本

`deploy/acceptance/remote_trial.py` 使用 Python 标准库，Windows 内置 OpenSSH `-F NUL`、显式私钥与 pinned known_hosts、严格主机校验；管理员口令交互读取，仅经 SSH stdin，cookie/普通随机口令不落盘、不打印。示例（不含秘密）：

```sh
python deploy/acceptance/remote_trial.py inspect --key '<KEY>' --known-hosts '<PINNED_KNOWN_HOSTS>'
python deploy/acceptance/remote_trial.py preserve --key '<KEY>' --known-hosts '<PINNED_KNOWN_HOSTS>'
python deploy/acceptance/remote_trial.py baseline --key '<KEY>' --known-hosts '<PINNED_KNOWN_HOSTS>'
python deploy/acceptance/remote_trial.py import --key '<KEY>' --known-hosts '<PINNED_KNOWN_HOSTS>'
python deploy/acceptance/remote_trial.py clock --key '<KEY>' --known-hosts '<PINNED_KNOWN_HOSTS>'
python deploy/acceptance/remote_trial.py team --key '<KEY>' --known-hosts '<PINNED_KNOWN_HOSTS>'
```

`baseline` 是有写操作的中国合成试用初始化（保留密码策略，正常保存 zh/Shanghai、关闭两开关），不是通用迁移器；`import` 固定使用本节来源名，首次写入校验成功/重复/错误，以后校验幂等重复/错误。`clock/team` 新建小规模唯一合成记录并保留，`team` 遇失败立即退出、不绕门禁。主机 Python 3.6，日期解析已避免其没有的 `datetime.fromisoformat`。全部六 phase 已实测；`team` 最终版在远端真实通过，范围与限制见 §14.4。`preserve` 只读核服务/镜像/端口、ping、安全设置及固定五件完整文档 canonical SHA256，更新前后和深验后已三次一致；不会自动改镜像锁或修复不一致。

后续运维不要调用旧 `~/crm-trial/deploy/remote/trial.sh`。每条命令独立指定本次同一 staging 和原 runtime（以下前两条只读，本轮已通过；后两条只供故障维护，**未执行且不自动恢复旧坏版服务**）：

```sh
CRM_TRIAL_DOCKER_SUDO=1 CRM_TRIAL_RUNTIME_DIR=/home/dev/crm-trial/deploy/remote/.runtime sh /home/dev/c1102-reviewed-update-eaffe942/tools/deploy/remote/trial.sh maintenance-status
CRM_TRIAL_DOCKER_SUDO=1 CRM_TRIAL_RUNTIME_DIR=/home/dev/crm-trial/deploy/remote/.runtime sh /home/dev/c1102-reviewed-update-eaffe942/tools/deploy/remote/trial.sh check
CRM_TRIAL_DOCKER_SUDO=1 CRM_TRIAL_RUNTIME_DIR=/home/dev/crm-trial/deploy/remote/.runtime sh /home/dev/c1102-reviewed-update-eaffe942/tools/deploy/remote/trial.sh maintenance-stop
CRM_TRIAL_DOCKER_SUDO=1 CRM_TRIAL_RUNTIME_DIR=/home/dev/crm-trial/deploy/remote/.runtime sh /home/dev/c1102-reviewed-update-eaffe942/tools/deploy/remote/trial.sh restore-old-lock --confirm-site-image-update
```

## 15. 既有 daemon 开机自启收口（2026-11-05）

本次仅获准启用服务器既有 Docker/containerd systemd 单元的开机自启，不是正式版本升级。沿既有 SSH 身份与 pinned known_hosts 严格校验成功，无 ACL 或访问方式调整；未读取私钥正文、口令或完整敏感配置。

| 检查 | 执行前 | 执行后 |
|---|---|---|
| `systemctl is-active docker.service containerd.service` | 两者 active，exit 0 | 两者 active，exit 0 |
| `systemctl is-enabled docker.service containerd.service` | 两者 disabled，exit 1 | 两者 enabled，exit 0 |
| 既有项目 `crm-trial-c010400` | 9 个长驻 running，configurator/create-site exited | 状态不变 |
| 全部 11 容器逐项比较 | 记录完整 ID、状态、StartedAt、RestartCount、OOMKilled、restart policy | 前后完全一致；RestartCount 均 0、OOMKilled 均 false |

唯一变更命令为 `sudo -n systemctl enable docker.service containerd.service`，exit 0；输出仅新增 `/etc/systemd/system/multi-user.target.wants/` 下指向既有 `/usr/lib/systemd/system/docker.service` 与 `containerd.service` 的两条 symlink。没有 `--now`、start/restart、整机重启、新建系统服务或修改既有 service 策略/配置；没有变更镜像、maintenance、DB 或测试业务。

长驻容器仍为 `unless-stopped`，两历史一次性容器仍为 `no`。本次只证明开机启用标志已设置且当前容器未受影响，**未实测宿主重启，也不证明重启后的应用/socket readiness**。M9 精确 24e 候选的 fresh 安装、部分失败维护恢复、正常 stop/up 数据保持及 HTTP/Engine.IO/WebSocket 证据属于其独立验证；正式版本仍未上线，不能把本次 enable 记成候选部署或正式发布完成。

## 16. 最终 24e 候选真实上线尝试：镜像加载失败，保留维护（2026-11-08）

正常 v1 权限限定交付门获独审批准后，主控明确授权对既有合成试用站执行升级；不迁入客户库、不宣称完整安全认证。前置最小只读确认：旧四 app、`fb00dd79…`、runtime ready、9 长驻运行、Docker/containerd active/enabled、磁盘余25G。严格合成开关/禁邮件保持。最初旧命名启发式漏掉 Lead00010，限定只读核对后与 `docs/qa/browser-e2e-2026-11-03/evidence/OBSERVATIONS.md:77-87` 的独立 fork 合成CSV导入同ID、21:27–21:29及管理员创建来源匹配；未据命名认定真实资料，也未修改记录或放宽guard。

交付精确工具 `242161c4ec0eb01825a9ee9e5ef6525770d27b7d`，本地 git archive 仅导出 deploy/remote，tar SHA256 `7959c93169613a78815db58c9eadf530d75bdd7f40998e97b2cc077e9ff2b8ec`，新 staging `/home/dev/c1108-reviewed-tools-242161`。候选在 `/home/dev/c1108-candidate-24e/candidate-release`：index `sha256:24e36e994c44fe497178f2e133e780cd2b2637a4e2d65f46bd5691400937f978`，config `sha256:41a88ded3dc8ac55cab451ff6b3c0b605968b971f28f726d38c0b1378b84b36e`。image.tar 1,576,683,520B，SHA256 `23b3fb65569912ce2bc82761af236d5ba34cf1781251cba6f5a60f0d906c1966`；release.env `836af4cfca2e25784f22de31b8c16ce4413c983c2d44c66353d985409187e984`；140层清单 `5f62d350a3094734bbb955d5975875b1c735ead6e58b6ef34ebd7b59525a0a79`。严格SSH/SCP后各文件SHA与本地一致。首轮tar传输60秒超时留下579469312B部分文件，原样改名为 `image.tar.partial-first-timeout` 保留；第二次完整传输约153秒exit0、SHA正确后才执行，不拿部分文件升级。

升级前六类全部完整doc canonical摘要存于本worker ignored runtime `m17-final-before.stdout.log`：Lead10、Deal3、Organization5、Contact21、Task7、Note13，仅输出数量/摘要，不输出业务正文。调用如下唯一正常入口：

```sh
CRM_TRIAL_DOCKER_SUDO=1 CRM_TRIAL_RUNTIME_DIR=/home/dev/crm-trial/deploy/remote/.runtime \
sh /home/dev/c1108-reviewed-tools-242161/deploy/remote/trial.sh upgrade-site-apps \
  /home/dev/c1108-candidate-24e/candidate-release \
  /home/dev/c1108-candidate-24e/candidate-release/image.tar --confirm-site-app-upgrade
```

**真实exit1，约132秒：** archive index→manifest→config及每个解压diff_id校验通过，停止写入服务，原生新备份 `20261108_013716-crm_localhost` 四件成功且可读验证PASS后停止backend；随后 `docker load` 报 **`max depth exceeded`**。未进入候选app安装/migrate/schema或上线readiness，不能宣称24e已部署。该现象发生于真实目标镜像加载，具体存储/层深根因尚未扩大诊断，不能把M9本地通过替代远端成功。

工具失败收口实测：全项目停止，原锁/元数据恢复，状态为 `maintenance reason=exit-1 image=sha256:41a88ded3dc8ac55cab451ff6b3c0b605968b971f28f726d38c0b1378b84b36e stop=stopped lock=restored metadata=restored`；活动锁恢复 `fb00dd79…`。只读复核全部项目容器exited，包含DB/双Redis；保留两个正常退出的查询one-shot。frontend/scheduler/websocket退出码137是本次stop后所见，不据此推断OOM。没有自动启动旧缺app镜像、重试load、删除卷/镜像、切存储驱动或恢复覆库。原数据升级后摘要未能复核（站点停服），不把备份可读说成恢复或数据全等已验。

本地原始工具输出：`P:/CRM/.tower/worktrees/wt-17/deploy/.runtime/m17-final-upgrade.stdout.log`；失败只读状态：同目录 `m17-final-failure-state.stdout.log`。均ignored，记录工具/摘要而非凭据。主控已收到即时失败报告，后续修复候选或同代恢复须另明确授权，不能使用跨代入口抢跑。当前Windows既有隧道映射仍为本地18088→远端127.0.0.1:8088，但服务维护停止，登录/CRM/日程不可作为可用入口；成功恢复后才验 `http://127.0.0.1:18088/login`、`/crm`、`/team-schedule`。宿主重启、完整权限安全矩阵与浏览器全流程边界不因此补算通过。

### 16.1 获准恢复旧四 app 可用（同日，非候选上线）

M13 核明失败在 pre-schema load，主控另明确授权恢复。执行前严格核旧 `fb00dd79…` 锁、上述完整 `maintenance exit-1` 字符串，活动release/layers与本代保留旧元数据逐字相同；升级原始日志未进入候选configurator/install/migrate。沿既有已验证 `/home/dev/c1102-reviewed-update-eaffe942/tools/deploy/remote/trial.sh`，每条显式 `CRM_TRIAL_DOCKER_SUDO=1` 与原 `CRM_TRIAL_RUNTIME_DIR`，执行 maintenance-status/check/up/status/versions/ping；不修改或重新上传工具。

check 通过 config/平台/三labels/全部diff_ids；up exit0，九长驻恢复运行，configurator正常exit0，六app仍旧fb00。versions/installed_apps精确为 frappe、crm、resource_import、team_access，未安装team_schedule。up后首个即时ping返回502，说明旧up只保证容器运行而不保证HTTP已就绪；随后限定只读核站点maintenance_mode未设（None），再正常ping得到200/pong，没有修改维护开关。此非持续故障或通过解除维护绕检查。

恢复后重新运行同一只读摘要脚本，六类全部完整doc数量与canonical SHA、原四app集合输出与升级前日志逐字全等：Lead10 `edc6028f…94ea`、Deal3 `2ecbb35c…701c`、Organization5 `7e5a1720…5e82`、Contact21 `4fb7fe5e…6905`、Task7 `bf813074…8beb`、Note13 `4cdf635d…47f1`；严格synthetic/mute/server_script开关断言仍通过。before/after完整摘要在ignored `m17-final-before.stdout.log` / `m17-old-restore-after.stdout.log`，启动原始输出为 `m17-old-restore.stdout.log`（该日志含首ping502，整体命令exit22，不能把它伪记整组exit0；up本身exit0，后续独立ping通过）。

**当前旧版保持运行，失败maintenance记录原样保留**，其中 `stop=stopped` 是失败时历史结果，不是当前实时状态；未删state或伪造ready。无install/migrate/restore、无DB覆库/卸app/权限关闭、无daemon或宿主重启。Windows既有隧道本地18088→远端127.0.0.1:8088，旧版入口 `http://127.0.0.1:18088/login`、`/crm` 已可接续；team_schedule尚未安装，不提供新日程上线承诺。24e仍未上线，等待低层兼容候选与下一明确部署指令。

## 17. 两层等值候选真实升级成功并常驻（2026-11-08）

主控明确接受M9两层候选与24e的fullConfig/有效rootfs内容、权限、链接等值，以及已记录目录mtime/rootheader元数据差；不重构建/本地矩阵。精确冻结：index `sha256:e17300da434bd0c251adf618c86db26c718511fec6ab6bfe2a99e7fd91bebe41`，platform `sha256:b240a3ef34502cb198f2b6abb07fe82ed542bd4032ae1fd4b1ca139299b28b60`，config `sha256:caf102a5716f4be0fc16ac9590038867bbe34c8e5419ff9fa92753ed6f1bf6d9`。新独立交付目录 `/home/dev/c1108-candidate-ld2/candidate-release`，tar 1,530,942,464B，SHA256 `6d67a6fd359b3fe69489e2e7e52bfbbedf7f9f289172d19751e2f732c7a0608b`；release `bce83c5d9acc14dafac0525b74fe8548ffc29eb04c77642dbc75651fa6ff1792`，两层清单 `f301343d0bf834ae563c4404adfaf8b1df0bcc811aa8e06951514dac657697e9`，manifest `e0e3c37f4598c93e6b1a9eed8b5d5303d096bc840e866c0c103992503c62b648`。900秒预算严格SSH/SCP传输约156秒exit0，四件本地/远端SHA逐项一致，未覆盖旧候选或删除旧失败证据。

执行前核旧fb00六app仍运行，原B=41a8失败maintenance及原证据保留，六类before摘要与§16前基线全等。复用原已审精确242161工具：其跨代分支先启动/核DB和双Redis，再停止frontend/websocket/queue/scheduler及backend，load后候选one-shot configurator→新备份，随后才install/migrate。因此当前旧服务已up并不绕过停写；未伪ready或删state。真实命令：

```sh
CRM_TRIAL_DOCKER_SUDO=1 CRM_TRIAL_RUNTIME_DIR=/home/dev/crm-trial/deploy/remote/.runtime \
sh /home/dev/c1108-reviewed-tools-242161/deploy/remote/trial.sh upgrade-site-apps-from-maintenance \
  /home/dev/c1108-candidate-ld2/candidate-release \
  /home/dev/c1108-candidate-ld2/candidate-release/image.tar --confirm-site-app-upgrade
```

**真实exit0，约286秒。** archive全链及两层解压diff_id校验通过，目标classic load成功；新原生备份 `20261108_034522-crm_localhost` 四件完成且可读，原备份保留。仅缺失team_schedule执行标准install-app，一次标准migrate，精确五app、七表/索引/longtext等工具schema验证PASS；DB身份、凭据及非维护site_config指纹等由标准工具保留核验。双Redis按已审config-hash/固定镜像/原数据卷契约更新健康检查并记录代次证据，不误称其容器ID不变。未init、迁客户库、删除卷、关权限或发信。

独立升级后只读复核：installed_apps精确frappe/crm/resource_import/team_access/team_schedule；六类完整doc canonical摘要与before逐字全等（Lead10、Deal3、Org5、Contact21、Task7、Note13），包括§16记录的六个完整SHA。严格synthetic_only整数1、mute_emails整数1、server_script_enabled0断言保持。backend和frontend内部HTTP ping均200/pong，远端回环8088 ping200；Engine.IO polling得到有效握手，WebSocket HTTP101升级通过，**仅为transport连通，不替代认证namespace/权限验证**。

最终 `ready image=sha256:caf102a5716f4be0fc16ac9590038867bbe34c8e5419ff9fa92753ed6f1bf6d9`，活动锁相同；六长驻app全同config，configurator exited0；9长驻运行，DB/双Redis/backend/frontend healthy，队列/scheduler/websocket不额外声称配置了healthcheck。新one-shot全部exited0并保留。再次check通过平台、三labels与全部RootFS层。**成功保持服务常驻，没有演练finally停站**。旧24e失败、旧锁/镜像/备份/工具均保留；不把既有备份可读当恢复演练。

本轮原始输出在worker ignored runtime：`m17-ld2-upgrade.stdout.log`、`m17-ld2-before.stdout.log`、`m17-ld2-after.stdout.log`、`m17-ld2-final-state.stdout.log`；不含口令/cookie。Windows既有隧道仍为本地18088→服务器127.0.0.1:8088，准确入口 `http://127.0.0.1:18088/login`、`/crm`、`/team-schedule`。已通知主控交Terra做Windows最小UI验收，本worker未抢跑业务UI或新增测试数据。正常v1权限仅为限定发布批准，不宣完整安全认证；宿主重启、全部安全旁路、长期容量、Windows本轮真实UI仍各有边界，未因此补算通过。

### 17.1 Windows普通UI验收账号夹具

主控明确授权新增唯一合成普通账号 `v1-ui-acceptance-20261107195038@example.invalid`，用标准框架User insert及fresh get重读验证：业务角色恰Sales User、enabled System User、send_welcome_email=0；创建前核mute_emails与synthetic_only仍严格整数1。没有额外管理员/System Manager角色、没有修改任何既有账号密码/角色，不删除旧用户，也未通过API创建Lead/日程。

随机强口令仅内存生成，凭据写入本worker独立ignored runtime文件；文件创建时关闭Windows ACL继承并仅当前用户FullControl，写后再核ACL通过。密码未输出stdout、Tower消息或Git，受保护文件准确路径已单独交Terra用于正式目标18088正常UI验收；文档不复制凭据。新增账号仅为验收夹具，UI验证结果由Terra独立记录，不把创建/角色检查冒充已通过业务UI。

## 18. M37 最终 UI/品牌/中文镜像正式更新（2026-11-08）

M37 最终4d59623获限定交付独审clean/merge，主控明确批准服务端/exe同步推进。本轮复用caf102五app ready、健康与空间基线，不重建、不做schema迁移/权限大矩阵，不重查已证合成来源。默认System Settings.language原已zh，未重复保存，也未改User语言/时区/密码/业务或网络。

冻结包上传到新独立 `/home/dev/c1108-candidate-2f92/candidate-release`，900秒预算约157秒exit0。四件远端SHA与冻结值全部相同：image.tar 1,540,059,136B `0deba5793481799ae1774d37926def678f35d8a1372eadaf09e31d55a144ccae`；7字段release `6a961af6a88356b529e34310559ee07beb09df57bf56de81cf6e8600710b9453`；7层清单 `225d78e8eee4dea16a4613ac2ea372dcf288e6d2ca2f75c2ce4822a5f7a98e33`；manifest `6184ff568ed0722b47d4399bcd64ba9f04acd5904930c0ec0cc3cfca864f8292`。index `sha256:2f92c460d47948bf6f030e23b24687b82ca3a92c4af4b8a200da7de7ac97db1b`，config `sha256:50a654164666adafc4f35c7a14b950b13cfba43363ce977aaa315461a0fd7987`。team_access label531是已核继承基线，明确含request.py固定access query品牌增量，不将其说成整个app零改。

```sh
CRM_TRIAL_DOCKER_SUDO=1 CRM_TRIAL_RUNTIME_DIR=/home/dev/crm-trial/deploy/remote/.runtime \
sh /home/dev/c1108-reviewed-tools-242161/deploy/remote/trial.sh update-site-image \
  /home/dev/c1108-candidate-2f92/candidate-release \
  /home/dev/c1108-candidate-2f92/candidate-release/image.tar --confirm-site-image-update
```

**标准image-only真实exit0，约146秒。** 停写前完整业务摘要已存；工具全archive链核通过，停止写服务，新原生四件备份 `20261108_225903-crm_localhost` 完成且可读，然后load/重建同镜像应用/readiness/ready。没有install/migrate/schema变更，旧镜像/备份/工具与失败历史保留，不宣备份恢复实测。

升级后六类全部完整doc数量+canonical SHA与本轮before逐字全等，原五app集合不变。独立核ready与活动锁均新50a654；六长驻应用及configurator均精确新config，前六运行、configurator退出0，restart0/OOMfalse，backend/frontend healthy；无healthcheck服务不虚报healthy。回环8088 ping200/pong；System Settings.language仍zh，未写。

仅普通测试账号正常HTTP登录/读取/logout，无浏览器和业务写入：真实CRM HTML包含最终 `index-1L7LpzFF.js`及完整 `/assets/team_access/access.js?v=7d26cdb3a226da9094e9e2f7ed5b1aadef2790de46fc0c3d47fea244bee043d6`；按最终static-receipt对11重点URL（登录主题、CRM入口JS/CSS、品牌manifest、裸/带query access、活动脚本、共享主题/中文脚本、日程JS/CSS）逐件实测HTTP200、bytes/SHA完全相同。不是只核裸asset或磁盘文件，不把资源SHA当视觉截图。凭据仍仅既有受保护ignored文件，未输出秘密。

**服务保持常驻**，Windows既有18088→远端127.0.0.1:8088，入口 `/login`、`/crm`、`/team-activities`、`/team-schedule`。已交主控安排Terra简短真实目标确认，本worker未并行UI。登录视觉截图未取得、活动入口局部白黑风格偏差、未全面多语言矩阵与权限限定批准边界均保留，不宣全视觉完美/完整安全认证。本轮原始证据在ignored `m17-2f92-{before,upgrade,after,static,final-state}.stdout.log`。

## 19. M42 漏译镜像已上线；公网 HTTPS 前置仍阻塞（2026-11-09）

主控批准使用精确已审M43 `64daf948aff3e24b411511f5c992474a203cbc94`（非冒称分支依赖已合并）。其deploy/https+deploy/remote+runbook的Git归档SHA256 `5a701ebee75da8256d59052b8e2d28738ea82279fb537fa08d62e14779d4e961`，SCP后相等，新staging `/home/dev/c1109-reviewed-https-64daf948`。其中trial.sh SHA `53d9eee8525efae3fb4ecd75cf1cbe87b62aa0a941ca9f06b4a8696dc89cc8d9`；不称原242161字节，53件SOURCE_SHA256SUMS不含它。旧工具/Compose/镜像锁快照保存在root-only `/var/backups/crm-https-h010-64daf948`，未复制或输出凭据。

M37 f4f2cd1的35d0冻结包上传到 `/home/dev/c1109-candidate-35d0/candidate-release`，900秒预算约158秒exit0，四文件逐SHA匹配：tar1,548,928,000B `45db442cc3c1614fcc8cafe9d56960fc22199f7d88b1ebcfc3ec6ce24eb39fe9`；release `dac7d52073d4252a4e42960860a3fa73f6241c2a5064a382e42eb7a0e8af6fe1`；13层清单 `f3ec8f1e58f827572bbf1c3a0753c64080de2b75e7b588b61a5fe1d87a6622b4`；manifest `98a93883e0998cc65a32022a7fb0f9486f245253536b6e23d8a2b23c039b7204`。index `sha256:35d0b0bd36ae08fa9d434b4275cb50bc4e202607c5f8ad95a34e6441c4922101`，config `sha256:310b0d22992ac555ea577f2fdc770f9adc0e21191d9d7e1855c6edd2d230649d`。

用上述64daf948新工具、原runtime、正常 `update-site-image <35d0 release目录> <image.tar> --confirm-site-image-update`，**真实exit0约144秒**；标准停写/新四件 `20261109_010555-crm_localhost` 备份可读后加载，未install/migrate。最终ready/锁均310b0d，六app同config运行、backend/frontend healthy，DB/双Redis仍healthy，8088仍仅回环。全部六类完整doc数量+canonical SHA及五app集合与本窗口 `m17-https-before.stdout.log` 逐字全等；System Settings zh、User语言/时区/密码/业务未改。普通已有合成账号仅HTTP login→实际CRM新 `index-DO9vnRFq.js` 与原access query→11重点静态bytes/SHA匹配35d0 receipt→logout，未浏览器/业务写入。原始输出ignored `m17-35d0-{upgrade,after,static}.stdout.log`。

### 19.1 已执行的 HTTPS 前置与阻碍（不冒称可用）

限定官方ALinux3启用签名源先assumeno核事务，再保持gpgcheck=1/sslverify=1安装nginx1:1.24.0-3.0.1.2.al8.1及其logos/filesystem，必要升级OpenSSL1.1.1k-17.0.1.al8与CA包；未装宿主Python/改alternatives。安装前后Python3.6.8、链接 `/usr/libexec/platform-python3.6`、所属python36 RPM一致。原Nginx默认server块保存原文件后仅移开默认块，其他配置保留，审定manage/http/tls已安装；nginx-t通过。Nginx active/enabled，目前只0.0.0.0:80提供ACME challenge/固定HTTPS308，不反代明文登录/API。

阻碍一：目标唯一一次拉固定官方Certbot amd64 digest `1dc5b4a99cce916f154c706569baf062600d7dea13e0711e7d7e1461d6230e39`，registry-1.docker.io/v2等待响应超时。主控批准第一Ubuntu等值离线转运后，本地唯一pull亦79秒失败（registry manifests HEAD，TCP443 i/o timeout），未save/load、未换源或改镜像/daemon。第一Ubuntu daemonID、容器/卷集合hash前后不变，不碰第二Ubuntu。尚无实际Certbot preflight或任何staging/production签证；不读私钥/ACME账号。主控已将公开官方Registry供应制品可行获取交M43，不盲重试。

阻碍二：Windows外网直连随机challenge一次20秒连接超时；同一服务器本机正确Host challenge200且内容相等，探针已删，本机/login308，ss确认0.0.0.0:80，主机INPUT ACCEPT、SELinux Disabled。**仅疑似云安全组/上游入站阻碍，未断言具体安全组**。需实例所挂安全组入方向TCP80供HTTP-01公开验证、TCP443供实际HTTPS访问；无需开放8088/8000/9000/DB/Redis。未关防火墙/猜云凭据/改云设置；443尚未监听不能当其云端失败证据。

因此目前**35d0旧回环访问可用且常驻，公网HTTPS尚未开通**：没有可信证书、443未激活、timer未安装、overlay未启用，尚未执行HTTPS登录/cookie/CSRF/认证socket或Terra直接HTTPS验收。OTA仍disabled，无虚假manifest/签名包发布。后继待镜像制品与80公网可达后按原审定步骤续行；不明文公网登录降级，不把本次后台SCP当用户端仍需SSH的最终方案。

### 19.2 官方Certbot离线制品到达，仍需寻址兼容

M43随后通过Windows官方Registry HTTPS一次获取完整制品，主控批准SCP/标准load：tar196,956,160B，双端SHA `feb4ef11bc19fee9e39c5579e85c0c481a6aec03f7d0819b68cdbf4ddd59dc19`，保存在新staging `certbot-official.tar`。目标load成功ID `sha256:f0cfa0056d76325c6a2d3f4dc4dc41449763a9ee1000ed11caf8dc180450144d`；实际11有序diff_ids和所有原始Config字段与官方config全等。Docker26 inspect额外补充旧式空/false字段，因此最初严格整个Config对象相等断言不等，后按原始字段逐项核实通过，未篡改原config。

RepoDigests实际为空，原 `certbot/certbot@sha256:1dc5…` inspect明确No such image；没有伪造tag/RepoDigest或改已审manage引用，未越过preflight。精确结果已交M43做最小config-pinned兼容并审定。该制品已到达不表示签证或HTTPS已成功，公网80阻碍仍保持。

### 19.3 离线寻址兼容真实无网 preflight 通过

M43 `3ec8f0919062e33084918ffdef080cb1dbda490c` 获seq144限定clean/merge后，主控仅授权最小无网preflight。Git archive导出deploy/https与runbook，81,920B，SHA256 `06db9f2155a92a525e3e900e77ab34e3b44eb0d4772050f7a6f2856302eaa7e5`；上传全新 `/home/dev/c1109-reviewed-https-3ec8f09/source.tar` 并核相同SHA，未覆盖旧staging或将新manage安装为系统活动版本。

仅执行 `sudo -n /usr/bin/python3 /home/dev/c1109-reviewed-https-3ec8f09/deploy/https/manage.py preflight`，真实exit0（约7秒含小包传输）。脚本核宿主固定/usr/bin/python3兼容3.6、nginx>=1.19.3、已load官方config f0cfa005及全部11有序diffids；随后以network none、只tmpfs、read-only/cap-drop/no-new-privileges短命容器运行，实报 **Python3.12.10 / certbot5.4.0 / crm-https preflight: OK**。宿主既有Python3.6.8/nginx1.24.0未更换；容器由本次--rm结束，不触原卷。

本次没有重新pull/load、重部署35d0、业务写入、签证、公网80探测、443/timer激活或数据库/权限修改。签证工具运行前置已通过；公网80可达阻碍及云安全组待确认状态仍在，**不将preflight通过冒充证书签发或公网HTTPS可用**。

### 19.4 用户告知云放行后的单次公网复核仍未通过

用户明确告知80/443已放行后，按主控续行授权只创建一个随机公开challenge文件并设0644，从Windows无代理直连 `http://8.133.190.46/.well-known/acme-challenge/<随机token>`；仍在TCP连接阶段20秒超时，没有取得HTTP响应。finally已仅删除本次探针，未循环探测。该次失败发生在后续命令之前，故没有将3ec8f09 staged manage安装成活动脚本、没有申请staging/production、没有激活443/overlay/timer或重部署35d0，原服务保持。原始失败输出在本会话agent420的task `bash-atu70h6l/output.log`。

此事实不等于断言用户没有设置安全组，也不证明是哪条网络策略；最近已有服务器本机challenge200/0.0.0.0:80/INPUT ACCEPT事实可复用。需核放行规则确实绑定公网IP所在实例且入方向TCP80允许公众CA验证来源（通常0.0.0.0/0，仅80静态challenge与HTTPS跳转）、443允许期望用户来源，避免只改其他安全组或仅放客户端来源。没有云权限则报告，不关闭防火墙、扫端口或降公网HTTP登录；继续保持未签证/HTTPS不可用边界。

## 20. 可信真实 IP HTTPS 已上线（2026-11-10）

本轮用户再次确认云规则后，重新核Nginx active/nginx-t成功、80监听、主机INPUT ACCEPT、CRM pong。一次随机HTTP-01 challenge本机及Windows无代理公网均200且内容相等，删除仅本次探针；有界仅SYN/SYNACK头观察证实请求抵达主机，不捕获业务载荷。此前公网连接超时阻碍现已解除，未改云账户/防火墙/业务或重复镜像部署。

将已审 `3ec8f0919062e33084918ffdef080cb1dbda490c` 的manage.py按精确字节安装到 `/usr/local/lib/crm-https/manage.py`，SHA256 `6023b2528645130569873a685ed5964a228cef44f13570602e36508b2b76695e`，旧文件root-only备份保留；原HTTPS保留trial仍为64daf948来源及§19所记SHA。无网preflight旧通过可复用，没有新pull/load。显式无邮箱登记，隔离staging一次成功后production一次成功，均使用固定官方config f0cfa005与其11层守卫；没有循环申请/force-renewal或容器host hook，未读取/输出证书私钥或账号秘密。

生产证书公开信息：Let's Encrypt **YE1**，critical IP SAN **8.133.190.46**，`notBefore=2026-11-10 02:14:09 UTC`、`notAfter=2026-11-16 18:14:08 UTC`，寿命不超过160小时；SHA256 fingerprint `72:05:06:C1:6F:D4:6C:BD:2B:2F:45:53:AC:96:58:3B:40:2B:5D:B6:17:8D:FB:E2:10:97:FE:58:DC:C8:91:6B`。证书/私钥匹配、IP SAN、系统信任链、剩余有效期及实际服务leaf均由审定activate/check验证，Windows正常系统信任HTTPS亦通过，无-k/证书忽略。该leaf会正常续期轮换，客户端不固定本leaf。

受控安装持久 `/etc/crm-https/{compose.yml,prepare_inner.py}`，合并Compose config --quiet成功，只重建backend/frontend，当次镜像模板严格守卫及内层nginx-t通过；原镜像35d0/config310b0d不变，其他应用/DB/双Redis未重建、无迁移/删卷。宿主nginx-t成功后activate443；ss最终22/80/443与127.0.0.1:8088，DB/Redis没有新增主机发布。80只challenge/固定HTTPS跳转，外来socket Origin403，错误Host策略保留。host_name/ssl_proxy及common回调备选均未设置，真实认证socket公网hairpin已可用，无需改公开配置或重启websocket。

### 20.1 真实公网最小功能验证

准确入口为 **`https://8.133.190.46`**，不再要求用户本机SSH/18088。用既有受保护普通Sales User凭据正常HTTPS登录，sid仅核属性：Secure、HttpOnly、SameSite=Lax，domain为公网host不含内部站点；身份正确。合法CSRF正常同值自有User.first_name保存200，保持语言/时区/密码不变；一次错误CSRF保存拒绝且没有业务写入。随后同cookie Engine.IO会话发正常Socket.IO `/crm.localhost` namespace连接，收到认证连接ack（不是仅101或匿名open），正常关闭本诊断transport并logout；cookie/token/密码值不输出。登录与跳转未出现内部/http降级URL。

11重点公开资源从Windows直接HTTPS读取200、bytes/SHA全匹配35d0冻结receipt，含新index-DO9vnRFq、主题/品牌/中文/日程和完整access query。HTTP `/login`308到固定HTTPS；未发布 `/updates/windows/{manifest.json,manifest.sig}` 均404，OTA仍disabled，不造清单或签包。此为HTTP与身份/认证连通检查，不冒充Terra视觉确认或完整权限安全认证。

业务最终只读：Lead11、Deal3、Organization5、Task7、Note13完整doc摘要与本轮既有before相同，五app集合不变。**Contact22数量未变但完整摘要不同**；限定只读metadata显示本轮唯一近期Contact修改时间11:14:19.477742，关联账号正是合成验收User，是正常同值User保存触发的Contact同步；不能称六类全部byte全等，也不反向伪造modified时间。没有删业务或改用户语言/时区，保留此测试夹具审计变化。

### 20.2 自动续期与运维边界

审定service/timer已安装，systemd-analyze verify通过；timer active/enabled，第一次renew service **Result=success / ExecMainStatus=0**，manage check0，剩余至少48小时、服务leaf匹配。初次next为11:19:51 CST（仅当时快照，之后按每小时17分加抖动执行）。无邮箱登记没有CA联系/邮箱提醒，运营需每日查看check退出码/failed unit或接已有监控，不能宣永不失败；本轮未另建告警平台。短命Certbot容器仅自动rm自身，原卷未动。

服务保持常驻。已立即向tower与M41直交可信origin/证书/正常登录与认证socket证据；M41将绑定真实HTTPS，真实签名安装包尚待其交付，不提前发布OTA。Terra后续仅简短直HTTPS检查主要入口。原始证据在ignored `m17-https-{staging,production,activate}.stdout.log`、`m17-public-https-verify.stdout.log`、`m17-https-final-docs.stdout.log`；均不含私钥/密码/cookie值。正式入口 `/login`、`/crm`、`/team-activities`、`/team-schedule`。

## 21. Windows 1.0.2 签名静态交付发布（2026-11-10）

M41 精确审定tip `d8139bfdfd2aa935783c35d0ad32b5a553c3842b` 获seq145静态发布/人工交付clean，整mission GUI hold不作绕过。本机只读三公开工件，先核bytes/SHA与固定SPKI公钥Ed25519精确manifest验签通过：keyId `746b9e5a91bea9de29f8eb061a2536e7`，manifest format philosopher-crm-ota-v1/version1.0.2/sequence1/win32/x64；公钥 `MCowBQYDK2VwAyEAql0KJJbJPvweE0CtfXkTxUoHCss7pJHF6i566RZnSL4=`。没有读取/上传签名私钥或客户资料。

三件经独立 `/home/dev/c1110-windows-1.0.2-seq1` 上传（约18秒），传前/传后三SHA相等，随后按exe先、配对manifest/sig顺序复制到全新root-owned `/var/lib/crm-public/releases/1.0.2-seq1/updates/windows`：

| 文件 | bytes | SHA256 |
|---|---:|---|
| PhilosopherStoneCRM-Setup-1.0.2-x64.exe | 121677059 | e9c766167e624e59b320e50acd92dff327e0d1c10c42a8f6a08cbaa30e369bca |
| manifest.json | 321 | 4dbb0ad8052d779d32a740da60a35228103308abd4380379ce17d289428fbdb3 |
| manifest.sig | 64 | 3383cd48e9c3ba9889402c40f9c5c9d1cc1e3b50be078429da3391d35714d670 |

此前静态root不存在，因此无旧exe/快照覆盖；父目录0755、文件0644且root owner，无group/world写，只包含三文件，不含任意文件symlink。完整快照核SHA后通过同文件系统临时链接→os.replace原子切换current，未重载/重部署CRM或重新签证。静态白名单现有Nginx配置直接生效，无目录浏览、非白名单404，POST拒绝；不把静态发布当客户端安装成功。

真实公开地址均为 `https://8.133.190.46/updates/windows/` 加上述文件名。Windows系统正常信任、Accept-Encoding identity逐件GET/HEAD均200，URL不变无重定向、无Content-Encoding、Content-Length精确；exe完整121,677,059B流式下载SHA与表一致（约286.8秒），一年immutable；manifest/sig完整原字节SHA一致、Cache-Control no-store，从真实HTTPS下载字节再次Ed25519验签通过。首轮180秒exe下载预算不足超时，未谎报SHA完成；第二次900秒预算完整运行约287秒exit0，不涉及重复发布。目录/非白名单404，POST拒绝。原始输出ignored `m17-public-release-verify.stdout.log`，三URL与证据已直接交tower/M41供其独立回验。

这仅证明可信静态供应链与人工安装包交付可用；**不宣GUI安装、未知发布者提示消除或真实自动升级成功**。安装器本体Authenticode NotSigned，Ed25519绑定不能冒充Windows发行者签名。未读/上传私钥、不重签证/CRM/数据库/权限矩阵；服务保持，后续客户端是否启用OTA按M41已审策略与主控交付结论，不由M17静态发布自行扩大。
