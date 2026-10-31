# 远端合成部署真实执行记录（C010600）

**状态：真实执行到镜像加载与凭据初始化，`trial.sh check` 门禁在目标主机失败并已按规则停止；站点、容器、卷、迁移与任何 HTTP/Windows 验收均未创建或执行。**

本文件只记录本轮实际发生的操作与观测结果。它**不是**生产批准，不解除 M8/M9 的权限与恢复门禁，也不把"镜像已加载"当成部署成功。失败点与根因见 §9，未执行项见 §11，需要决定的事项见 §12。

## 1. 授权与范围

用户明确要求"服务端部署上线，客户端安装，我在 win 下试试"，并授权在该服务器使用 sudo 安装 Docker/Compose 用于调试、部署与实际测试；M14 已完成安装并合并，M13 精确 `240b9a8b2ee23fba281cc2a987ec6246fd00109c` 经独审 clean/hold 明确可进入已授权独立合成实测。

| 本轮允许并实际执行 | 本轮禁止并未执行 |
|---|---|
| 只读现场复核（身份、资源、Docker、冲突、注册表可达性） | 修改、升级或重装 Docker/系统；`systemctl enable`；改组、改 sshd/防火墙/安全区/swap |
| 从精确 tip 取 M13 文件、复用已核证 M9 构建 context 组装交付 | 重新 build 镜像、改候选源码、改 `deploy/remote/*` |
| 本地导出镜像 tar、远传输与两端摘要核验 | 把 image ID 当 tar 摘要；上传仍在校验中的文件 |
| 远端解包、`verify-source`、`load-image`、`init-env` | 跳过门禁、忽略必填/权限、清库或重置后重试 |
| — | 创建站点/容器/卷、启动栈、导入真实资料、删改任何既有资源 |

## 2. 连接、主机身份与凭据边界

全程使用 Git Bash 的 `/usr/bin/ssh`，固定参数：`-o UserKnownHostsFile=…/m10-known_hosts -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o BatchMode=yes`。私钥只作为 `-i` 参数传入，**未读取、未打印、未复制、未提交正文**；本轮未在本文件或任何消息里出现私钥、密码或 `.env` 内容。

本轮重新计算专用 known_hosts 指纹：

```
$ ssh-keygen -lf …/m10-known_hosts
256 SHA256:JHFV75F2oc1tYqjd4viv130aknkd7fOwtKEpmGtgy80 8.133.190.46 (ED25519)
```

与 M10/M14 记录逐字符一致，且在 `StrictHostKeyChecking=yes` 下连接成功，说明出示的 key 就是记录中的 key。**这仍是 TOFU 记录，未做带外认证**；若日后变化必须停止。每次连接仍打印 "connection is not using a post-quantum key exchange algorithm" 警告，说明服务器 sshd 较旧，本轮未修改。

## 3. 第 1 关：现场只读复核（通过）

先只读核对主机、资源、Docker 与目标冲突，未创建任何资源（除 §5 的交付目录）。

| 项 | 实测值 |
|---|---|
| 主机名 / 内核 / 架构 | `iZuf6htx2n3srizz88227cZ` / `5.10.134-19.8.al8.x86_64` / `x86_64` |
| OS | `ID=alinux` `VERSION_ID=3`（Alibaba Cloud Linux 3） |
| 用户 | `uid=1000(dev) gid=1000(dev) groups=1000(dev),10(wheel)`；**不在 docker 组** |
| CPU | 2 |
| 内存 / swap | MemTotal 1870 MiB，可用 1532 MiB；SwapTotal 0 kB（无 swap，本轮未添加） |
| 磁盘 | `/dev/vda3` 40G 已用 5.1G 可用 33G；home 与 `/var/lib/docker` 同一文件系统 |
| sudo | `sudo -n true` 成功（免交互） |
| Docker 服务 | `active` / `enabled`？→ **`disabled`**（M14 只 start，未 enable，本轮未改） |
| Docker 版本 | server 26.1.3 `linux/amd64`；Compose v2.27.0 |
| 既有容器 / 卷 | **0 / 0** |
| 网络 | 仅 `bridge`/`host`/`none`；无 `crm_trial_c010400_network` |
| 监听端口 | 仅 `0.0.0.0:22` 与 `[::]:22`；**8088 未监听** |
| 目标目录 | `~/crm-trial` 不存在；`~/c010500-docker-install`（M14 审计暂存）存在 |
| 注册表只读探测 | `public.ecr.aws/v2/` → 401；`ghcr.io/v2/` → 401；`registry-1.docker.io` → 连接超时 |

401 只证明端点与 TLS 可达（正常的 auth challenge），**不证明真实 digest pull 会成功**；Compose 的 db/redis 固定使用 `public.ecr.aws` digest，本轮未发生 pull。

## 4. 第 2 关：交付准备与独立核证（通过）

### 4.1 源码 context

复用 wt-9 已核证的 `deploy/.runtime/integration-7d31d600dbcf49bbaf52b5c97dee6a42`（**未重新 build、未改任何 worker 源码、未读取未提交文件**）。M13 的 `deploy/remote/*` 与 `docs/REMOTE_TRIAL.md` 由 `git -C wt-13 archive 240b9a8b2ee23fba281cc2a987ec6246fd00109c` 取得，按 M13 §3.1 放入 context。

交付 tar 只含 `apps deploy docs source-manifest.json`，实际检查 `deploy/remote/.runtime` 不存在，也没有 `candidate-image.env` / `build-result.json` / 任何 `.env`、日志、站点、数据库或 session 文件进入交付。

### 4.2 独立核证（不只依赖 manifest 自证）

逐条用 `git -C <wt-9> show <commit>:<path>` 取**精确 Git blob**，与交付文件内容和 `deploy/remote/SOURCE_SHA256SUMS` 三方比对：

| 路径前缀 | 固定 commit | 条目 | 结果 |
|---|---|---|---|
| `apps/resource_import/` | `faa5f0330ad54bd9f4d02bb498ea305651c95ed9` | — | 一致 |
| `apps/team_access/` | `0e5fed78841f8acad31278a3e06cb08b0e6e93d0` | — | 一致 |
| `deploy/Dockerfile*` | `a1ce4ca143a20cecf13db7e490b79d0349c4d59c` | — | 一致（打包步骤按 M13 §3.1 做 CRLF→LF 规范化后才等值） |
| 合计 | | **53** | **53/53 相等，0 不符** |

三个 commit 的 `rev-parse <commit>^{commit}` 均等于固定值。

`source-manifest.json` 规范化 LF 后：

```
e4877bea2686eff52e8708751492e4a5ae5fc1cf8bd8c3de3e6951684df5b374  source-manifest.json
```

与固定摘要一致（打包前 59 处 CRLF 被规范化，记录在案，不是内容改动）。

### 4.3 镜像导出与交付摘要

镜像导出在第一 Ubuntu（Ubuntu-24.04）本地 Docker 完成。**注意状态区别**：该发行版 `systemctl is-active docker` 仍为 `activating`，但 daemon 真实应答（`docker image inspect` / `docker save` 均成功）；本轮只读诊断，**未重启、未重装**，未触碰第二发行版。

```
$ sudo docker image inspect sha256:cae67cc3…3ba0705 --format …
id=sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705
size=1539417571 os=linux/amd64 created=2026-10-31T20:21:45.582152094+08:00
labels: crm.resource-import.revision=faa5f033… / crm.team-access.revision=0e5fed78… / org.opencontainers.image.revision=36bd8859…
```

`docker save` 真实退出 0、tar 完整生成（1,539,445,760 字节）**之后**才计算摘要：

```
$ sha256sum crm-trial-c010400-source-and-tools.tar crm-c010400-image.tar
33caf5473b79b46b7c1b1fb25deef801cbabf56779d04c2853f7e9a234e159a4  crm-trial-c010400-source-and-tools.tar
a5588c193efce06e6e53591a3ce38046908c06c30c6cf097ba320387c545b7db  crm-c010400-image.tar
```

`DELIVERY_SHA256SUMS` 只含相对 basename；把整个 staging 复制到另一目录后 `sha256sum -c` 两件均 OK（摘要未重建、未改写）。镜像 tar 的传输摘要与镜像 ID 是两件不同的事，本文件不混用。

## 5. 第 3 关：传输与完整性（通过）

远端先以独占 `mkdir` 新建交付目录（不覆盖任何既有目录），再 `scp` 三个文件：

```
$ scp … DELIVERY_SHA256SUMS crm-trial-c010400-source-and-tools.tar crm-c010400-image.tar dev@…:/home/dev/c010600-delivery/
real 2m13.859s   SCP_EXIT=0
```

远端重新计算并核对：

```
$ cd /home/dev/c010600-delivery && sha256sum -c DELIVERY_SHA256SUMS
crm-trial-c010400-source-and-tools.tar: OK
crm-c010400-image.tar: OK
SUM_RC=0
```

即**传输前后摘要相同**，两个 tar 与本地生成物一致。

## 6. 第 4 关：只读预检（PREFLIGHT READY）

按指南从**同一个已核验 tar** 只提取两文件到独立非目标目录，不整包解压到目标目录：

```
PREFLIGHT_DIR=/tmp/crm-trial-preflight.8ZF2Wh
-rw-r--r-- docker.sh   -rwxr-xr-x preflight.sh
TRIAL_DIR_ABSENT_BEFORE_PREFLIGHT
$ CRM_TRIAL_DOCKER_SUDO=1 sh "$PREFLIGHT_DIR/deploy/remote/preflight.sh"
```

关键输出（原样摘录）：

```
PASS: x86_64 architecture
PASS: Alibaba Cloud Linux 3
INFO: MemTotal=1915884KiB MemAvailable=1575060KiB SwapTotal=0KiB
PASS: at least 1.5GiB RAM detected
WARN: no swap; this package will not add swap and cannot guarantee stability on a 1.8GiB host
INFO: free space on home filesystem=32166304KiB
PASS: at least 8GiB free on the home filesystem
PASS: command openssl / sha256sum / tar / ss / awk / df
INFO: host Python=3.6.8; application Python remains inside the pinned image
WARN: host Python is below 3.9 and is not suitable for M9 manage.py; remote shell tools do not require it
PASS: trial path is absent
PASS: Docker CLI exists
Docker Compose version v2.27.0
PASS: Compose v2 exists in the selected access mode
PASS: default local Docker context
PASS: selected mode can access the local Docker daemon
INFO: DockerRootDir=/var/lib/docker free=32166300KiB
PASS: volume absent: crm_trial_c010400_db / _redis / _sites / _logs
PASS: trial network absent
PASS: create-site container absent
PASS: no containers in the trial Compose project
PASS: TCP port 8088 is free
PREFLIGHT READY: proceed only after authorization; 1.8GiB/no-swap stability and all runtime acceptance remain unverified
PREFLIGHT_RC=0
TRIAL_DIR_STILL_ABSENT
```

`sudo -n` 模式生效，失败即停、无普通用户回退；预检前后目标目录均不存在。

## 7. 第 5 关：解包与 `verify-source`（通过）

```
$ mkdir "$HOME/crm-trial" && tar -xf /home/dev/c010600-delivery/crm-trial-c010400-source-and-tools.tar -C "$HOME/crm-trial"
$ cd "$HOME/crm-trial" && CRM_TRIAL_DOCKER_SUDO=1 sh deploy/remote/trial.sh verify-source
PASS: 53 exact app/build source files match M9 candidate sources
VERIFY_RC=0

755 deploy/remote/preflight.sh   755 deploy/remote/trial.sh
644 deploy/remote/release.env     644 source-manifest.json
e4877bea2686eff52e8708751492e4a5ae5fc1cf8bd8c3de3e6951684df5b374  source-manifest.json
```

远端 manifest 摘要与固定值相同；脚本以显式 `sh` 调用，余下文件不需要执行位。

## 8. 第 6 关：`load-image` 与 `init-env`（命令返回 0，但 ID 不符）

```
$ time sh deploy/remote/trial.sh load-image /home/dev/c010600-delivery/crm-c010400-image.tar
Loaded image ID: sha256:129b03571ac973784c7a3dab851ec31496db6b689bbbd8935337b068dea81c07
PASS: docker load returned zero; run init-env/stat/check to verify image identity and labels
real 2m5.075s   LOAD_RC=0
```

`init-env` 只执行一次，生成新的独立合成凭据，**值未打印**：

```
PASS: independent trial credentials and image lock created with private permissions; values not printed
INIT_RC=0
700 deploy/remote/.runtime
600 deploy/remote/.runtime/.env
600 deploy/remote/.runtime/image.env
CRM_IMAGE=sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705
```

## 9. 第 7 关：`check` 门禁**失败**并停止（本轮阻断点）

```
$ sh deploy/remote/trial.sh check
Error response from daemon: No such image: sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705
ERROR: exact candidate image is not loaded
CHECK_RC=1
```

`compose --profile setup config -q` 在失败前已通过；失败发生在镜像 `.Id` 比较。

### 9.1 现象与实测事实

| 观测 | 值 |
|---|---|
| 远端加载后的镜像 | `129b03571ac9 <none>:<none> 4.19GB`（无 tag、无 repo digest） |
| 远端 `.Id` | `sha256:129b03571ac973784c7a3dab851ec31496db6b689bbbd8935337b068dea81c07` |
| 远端 `.Size` / 平台 | 4,187,705,330 / `linux/amd64` |
| 远端 config labels | 三个 revision 与固定值**逐字符一致**（`faa5f033…`、`0e5fed78…`、`36bd8859…`） |
| 固定的 `CRM_IMAGE` | `sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705` |

### 9.2 根因：固定"镜像 ID"是 buildx manifest list 摘要

M9 自身构建日志（`wt-9/deploy/.runtime/candidate-build-7d31d600-r3.log`）已经写明：

```
#13 exporting config sha256:129b03571ac973784c7a3dab851ec31496db6b689bbbd8935337b068dea81c07
#13 exporting manifest sha256:6014c9df39452ce0cf0e6834822d7d1de89b814ef11f1d6e78bb1ea5c1f50a60
#13 exporting manifest list sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705
```

- 第一 Ubuntu 的 Docker 使用 **containerd image store**（`Storage Driver: overlayfs`，`driver-type: io.containerd.snapshotter.v1`），此时 `.Id` 报的是 **manifest list（含 attestation manifest）摘要** → 记录成 `cae67cc3…`。
- 目标主机是 Docker 26.1.3 **经典 overlay2 store**（M14 记录），`docker load` 只能按 **config 摘要**命名镜像 → `.Id = 129b0357…`。经典 store 的镜像 ID 定义就是 config 摘要，**cae67 在该 daemon 上不可能成为镜像 ID**。

因此 `release.env` 的 `CRM_IMAGE` 与 `trial.sh check` 的 `.Id` 比较跨了两个 digest 命名空间：这不是传输损坏、不是权限问题、不是资源不足，**同一条门禁在任何经典 store 主机上都会失败**。M13 只做过 mock（daemon 打桩），没有在经典 store 上跑过 `load → check`。

### 9.3 交付物本身已核验等价（不是"忽略校验"）

- 本地 tar 是合法 OCI layout：26 个 blob 逐个自校验 sha256 全部一致；`manifest.json` 的 `Config` = `blobs/sha256/129b0357…`；`index.json` 的 digest = `cae67cc3…`（固定值确实存在于交付物中，作为 index 摘要）。
- config blob 的 `labels`、`rootfs.diff_ids`（24 层）、`os/arch`、`created` 与本地镜像一致；远端加载后 labels/平台一致。
- 尺寸差异属口径不同：containerd 报压缩内容 1,539,417,571 字节，经典 store 报未压缩层合计 4,187,705,330 字节。**size 同样不能作为跨 store 的身份判据。**

即：交付的镜像**内容**与 M9 候选一致，差异只在 `.Id` 的命名约定（index vs config digest）与尺寸口径。

### 9.4 停止动作

按"失败即停、保留现场、不给错误路径绕过"：未执行 `create-site`、`up`、`backup`、`install-extensions`、`migrate`、`enable-import`；未创建任何容器、卷、站点或网络；未修改 `release.env`、`trial.sh` 或任何已审代码；未删除任何既有资源。

## 10. 现场保留资源（本轮创建，未清理）

| 路径 / 资源 | 状态 |
|---|---|
| `/home/dev/c010600-delivery/` | 两 tar + `DELIVERY_SHA256SUMS`；1.5G；`sha256sum -c` OK |
| `/home/dev/crm-trial/` | 解包源码树（596K），53 文件 `verify-source` PASS |
| `/home/dev/crm-trial/deploy/remote/.runtime/` | 目录 700；`.env`、`image.env` 均 600（新生成合成凭据，未打印）。`image.env` 现值锁定 `CRM_IMAGE=sha256:cae67cc3…`，不得重新 `init-env` 或覆盖 |
| `/tmp/crm-trial-preflight.8ZF2Wh/` | 预检脚本临时副本（仅两文件） |
| Docker 镜像 | 1 个未打 tag 镜像 `129b03571ac9`（4.19GB） |
| Docker 容器 / 卷 / 网络 / 站点 | **0 / 0 / 仅默认三项 / 无** |
| 磁盘 / 内存 | `/` 11G 已用、27G 可用；Mem used 413 MiB、available 1457 MiB |
| 监听端口 | 仅 22；**8088 未监听** |

## 11. 明确未执行（不得视为通过）

- **G1**：无四 app 集合、无 `bench version`、无两次 migrate 日志、无 9 服务运行、无 `docker compose ps`、无 HTTP `ping`、无 OOM/重启/内存观察。
- **G2**：无标准网页登录、无 System Settings 基线、无资产/MIME 核验。
- **G3**：无合成双用户、无权限矩阵；M8 完整矩阵与生产门禁**未因本轮推进**。
- **G4**：Windows SSH 隧道未建立（服务端未启动，隧道没有可转发目标）。
- **G5**：Edge PWA 安装未执行（同上）。
- **G6**：保留式 `stop`/`backup` 未执行（无运行栈）；恢复演练未执行。
- **未验证容量**：1.8 GiB / 无 swap 下运行 9 服务栈仍属未知；本轮只完成镜像加载与预检。

## 12. 阻断与决定

阻断点唯一：`trial.sh check` 的镜像身份比较跨 store 命名空间（§9）。现场完整保留，可继续或回退，不影响任何既有资源。

**tower 已决定（2026-10-31）：采用方案 A —— 修正 M13 的镜像身份契约、独审后再部署；不要求为这种可逆的兼容性修复另行取得人类批准。同时明确禁止方案 C（绕过 `check`）、禁止重建镜像、禁止切换 image store。**

| 选项 | 内容 | 状态 |
|---|---|---|
| **A（已选）** | 修 M13 包：门禁改为校验**交付 tar 的 sha256 + config digest `129b0357…` + 三个 revision label + `linux/amd64`**；`cae67cc3…` 只作为 index/manifest-list 出处摘要 | 完整证据链已交 `remote-deployment-package`；等其修包并独审后恢复本条线继续 |
| B | 在经典 store 上重建或 `skopeo copy --format docker-archive` 重导 | 禁止：等于换候选镜像 |
| C | 一次性程序性例外，越过该检查 | 禁止：不得绕过已审门禁 |
| D | 远端切换 containerd image store | 禁止：未授权的系统变更 |

**已存在 runtime 锁的迁移要求**：`~/crm-trial/deploy/remote/.runtime/image.env` 已在首次 `init-env` 中写为 `CRM_IMAGE=sha256:cae67cc3…`。修正后的包若改变镜像锁语义，必须先给出"已存在 runtime 锁如何被审查后迁移"的明确步骤（例如受控地只重写 `image.env`），再执行；**禁止重新 `init-env`、禁止覆盖或重建已生成的合成凭据**。

本地交付物仅影响 M15 未提交的 runtime staging，不改变 M13 已审文件；M13 的修正由该分支 owner 完成并重新走独审。

## 13. 凭据与后续 Windows 接入的信息边界

- **凭据只在远端 runtime**：`~/crm-trial/deploy/remote/.runtime/.env`（600，含 DB 与 Administrator 合成口令）、`image.env`（600）。本轮**未打印、未回传、未复制到本地或 Git**。安全获取方式：以 `dev` 身份登录后本地读取该文件，不要经命令参数、日志或聊天传递；`init-env` 拒绝覆盖，若确需重来必须先由人类决定如何处理已存在的 runtime。
- **Windows 接入尚不可用**：服务端没有运行中的站点，`127.0.0.1:8088` 未监听，因此现在建立隧道没有意义。待 §12 决定后继续时，接入前提固定为：只回环 `127.0.0.1:8088`、SSH 隧道到 Windows `127.0.0.1:18088`、专用 known_hosts + `StrictHostKeyChecking=yes`、`IdentitiesOnly=yes`、`BatchMode=yes`，且不放开公网端口。本文件**不**声称 Windows 已安装或可访问。

## 14. 只读复核清单（可安全重放）

以下命令全部为查询，不创建、不启动、不改配置（`<KEY>` 只作 `-i` 参数）：

```sh
ssh -i <KEY> -o UserKnownHostsFile=<m10-known_hosts> \
  -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o BatchMode=yes dev@8.133.190.46 'sh -s' <<'EOS'
cd /home/dev/c010600-delivery && sha256sum -c DELIVERY_SHA256SUMS
cd "$HOME/crm-trial" && sha256sum source-manifest.json
stat -c '%a %n' deploy/remote/.runtime deploy/remote/.runtime/.env deploy/remote/.runtime/image.env
sudo -n docker images --format '{{.ID}} {{.Repository}}:{{.Tag}} {{.Size}}'
sudo -n docker ps -a --format '{{.Names}} {{.Status}}' | wc -l
sudo -n docker volume ls -q | wc -l
sudo -n docker network ls
sudo -n docker image inspect sha256:129b03571ac973784c7a3dab851ec31496db6b689bbbd8935337b068dea81c07 \
  --format '{{json .Config.Labels}}'
ss -ltn
df -h /; free -m
EOS
```

Python 侧不复算凭据内容；`.env` 只需 `stat` 权限位，**不要 cat**。

## 15. 证据摘要

| 阶段 | 实际命令（摘要） | 结果 |
|---|---|---|
| 主机身份 | `ssh-keygen -lf m10-known_hosts`；`SHELL` 下 `hostname`/`uname`/`id`/`nproc`/`free`/`df` | 指纹一致；alinux 3、2 vCPU、1870 MiB、33G；Docker 26.1.3 active/disabled；0 容器 0 卷；8088 空闲 |
| 交付准备 | `git archive 240b9a8`（M13 文件）+ 复用 wt-9 context；`sha256sum source-manifest.json` | 53 文件与三个固定 commit 的 blob 逐一相等；manifest LF 摘要 `e4877bea…` |
| 镜像导出 | `sudo docker save sha256:cae67…3ba0705 > crm-c010400-image.tar` | 退出 0，tar 1,539,445,760 字节，摘要 `a5588c19…` |
| 交付清单 | `sha256sum … > DELIVERY_SHA256SUMS`；复制到另一目录 `sha256sum -c` | 两件 OK |
| 传输 | `scp` 三文件；远端 `sha256sum -c` | 退出 0（2m13s）；两件 OK |
| 预检 | 从同一 tar 提取 `preflight.sh`+`docker.sh` 到 `/tmp`；`CRM_TRIAL_DOCKER_SUDO=1 sh preflight.sh` | PREFLIGHT READY（exit 0），目标目录仍不存在 |
| 解包/源码 | `mkdir ~/crm-trial`；`tar -xf`；`trial.sh verify-source` | 53 文件 PASS |
| 加载镜像 | `trial.sh load-image …/crm-c010400-image.tar` | 退出 0（2m5s）；加载 ID `129b0357…` |
| 新凭据 | `trial.sh init-env`；`stat` | 700/600/600；值未打印 |
| 门禁 | `trial.sh check` | **失败 exit 1**：`No such image: sha256:cae67…` |
| 停止后状态 | `docker ps -a` / `volume ls` / `ss -ltn` / `df` / `free` | 0 容器、0 卷、仅 22 端口、27G 可用 |

**结论：本轮真实完成了主机复核、精确源码与镜像交付核证、传输完整性、只读预检、远端解包、53 文件源码校验、镜像加载与新凭据初始化；在 `check` 门禁因镜像 ID 命名空间不匹配而失败后停止并保留现场。服务端未上线、站点未创建、Windows 未接入、M8/M9 门禁未推进。后续按 §12 方案 A：M13 修正镜像身份契约并独审通过后，从 `check` 继续。**
