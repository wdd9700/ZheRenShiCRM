# 远端合成试用部署包（C010400）

**状态：仅供独立审查的部署候选，尚未上线。** 本轮没有连接 `dev@8.133.190.46`、读取私钥、传输源码/镜像、执行 sudo、安装系统软件或创建远端资源。远端安装、启动、登录、双用户权限、Windows 隧道和 PWA 验收全部未执行。

用途仅限**全新独立目录中的合成资料试用**：服务器只监听 `127.0.0.1:8088`，Windows 经 SSH 转发到 `127.0.0.1:18088`。不得导入真实客户资料，不得复用本地 `deploy/.env`、数据库、卷、Cookie 或会话。M8 完整权限矩阵和生产门禁不因部署成功而取消。

## 1. 固定交付与资源边界

| 项 | 固定值 |
|---|---|
| M9 部署工具来源 | `a1ce4ca143a20cecf13db7e490b79d0349c4d59c` |
| `resource_import` 来源 | `faa5f0330ad54bd9f4d02bb498ea305651c95ed9` |
| M8 `team_access` 来源 | `0e5fed78841f8acad31278a3e06cb08b0e6e93d0` |
| buildx OCI index 出处 | `sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705` |
| linux/amd64 平台 manifest | `sha256:6014c9df39452ce0cf0e6834822d7d1de89b814ef11f1d6e78bb1ea5c1f50a60` |
| 经典 store 可运行 config pin | `sha256:129b03571ac973784c7a3dab851ec31496db6b689bbbd8935337b068dea81c07` |
| 交付 image tar SHA-256 | `a5588c193efce06e6e53591a3ce38046908c06c30c6cf097ba320387c545b7db` |
| 镜像大小（仅 M9 containerd 口径） | 1,539,417,571 字节；不是跨 store 身份或 tar 完整性判据 |
| 应用版本 | Frappe 15.125.0 / CRM 1.90.0 / resource_import 0.1.0 / team_access 0.1.0 |
| 目录 / Compose 项目 | `~/crm-trial` / `crm-trial-c010400` |
| 独立卷 | `crm_trial_c010400_{db,redis,sites,logs}` |
| 网络 / 唯一发布端口 | `crm_trial_c010400_network` / `127.0.0.1:8088:8080` |

M9 构建日志逐项证明 config `129b0357…` → linux/amd64 manifest `6014c9df…` → manifest list/index `cae67cc3…` 的导出关系；M15 交付 tar 进一步证明 manifest 指向 config 和 24 层，经典 overlay2 加载后 `.Id=config`。containerd image store 的 `.Id` 则是 index。四种摘要用途不同：tar SHA 只证明交付字节，index/manifest 只证明 OCI 出处，config+RootFS diff_ids 才是经典 store 可运行内容锁；三个 revision label 只作附加断言，不能反推身份。

`deploy/remote/preflight.sh` 是只读预检；`trial.sh` 是后续运维入口；`compose.yml` 保留 DB、双 Redis、backend、websocket、frontend、双队列和 scheduler，不靠关闭重要服务凑启动。backend 仅按 M9 隔离恢复拓扑降为 1 worker / 2 threads，**这不是低内存可用性保证**。

M10 已知主机为 2 CPU / 1.8 GiB RAM / 无 swap。该栈同时运行 9 个长驻服务，可能 OOM、重启或无法完成迁移；33 GiB 磁盘也只表示当前空间，不代表持续备份容量。预检要求 home 和 Docker 文件系统各有至少 8 GiB 可用空间，作为镜像导入、数据库和短期备份的保守门槛，不是生产容量建议。不得擅自加 swap、停安全服务、清其他项目资源或降低权限来释放资源。

主机 Python 3.6.8 不用于运行应用或 M9 `manage.py`（其代码使用 Python 3.9+ 接口）。应用 Python 固定在候选镜像内；本包远端运维使用 POSIX shell、标准系统工具和容器内 Python，只有 `verify_image_archive.py` 显式兼容主机 Python 3.6 标准库用于离线摘要链核验。不要替换系统 Python 或另装解释器来绕过这些边界。

### Docker 访问模式（默认不提权）

M14 已在用户明确授权下安装 Docker 26.1.3 / Compose 2.27.0；`dev` 未加入 Docker 组，普通 `docker info` 会被拒绝。脚本默认 `CRM_TRIAL_DOCKER_SUDO=0`，不会自动提权。需要在该主机以 `dev` 部署时，显式设置：

```sh
export CRM_TRIAL_DOCKER_SUDO=1
sh /独立预检目录/deploy/remote/preflight.sh
# 后续 trial.sh 命令沿用同一导出值；恢复默认则 export CRM_TRIAL_DOCKER_SUDO=0
```

模式 1 只对 Docker CLI 使用 `sudo -n docker`，禁止 `sudo sh trial.sh`，不会把目录、凭据或备份的所有者改为 root。`sudo -n` 失败立即停止，没有普通/提权静默 fallback。两脚本均拒绝非空 `DOCKER_HOST` 和 `DOCKER_CONTEXT`，并要求 `docker context show` 为 `default`；`create-site` 把该模式显式传给子预检。不要用环境变量把操作重定向到其他 daemon。

## 2. 管理员安装清单（M14 已完成后的复现参考）

以下来源已经核对，但**命令本轮一条也没有执行**：

- 阿里云官方《[安装并使用 Docker 和 Docker Compose](https://help.aliyun.com/zh/ecs/use-cases/install-and-use-docker)》的 Alibaba Cloud Linux 3 专用路径：Docker CE 仓库、`dnf-plugin-releasever-adapter`、`docker-ce`、Buildx 和 Compose 插件。
- Docker 官方《[Install Docker Engine on CentOS](https://docs.docker.com/engine/install/centos/)》说明仓库安装、GPG 指纹和服务启动；便利脚本不建议作为本部署路径，本包不使用 `curl | sh`。

M10 已确认 Docker/Compose 不存在，因此不执行官方文档中的旧版卸载步骤。管理员仍应先复核实际机器没有 Docker 旧包或冲突仓库；若发现任何既有安装/数据，停止并保留现场，不能照搬卸载命令。

获得明确提权及系统变更授权后，由管理员在 Alibaba Cloud Linux 3 ECS 内执行。`curl`、`gpg` 必须已经存在，否则停止，不临时盲目安装其他工具：

```sh
# 先经 HTTPS 获取 Docker 官方 key；文件保留供审计，不是私钥
umask 077
curl --fail --location --proto '=https' --tlsv1.2 \
  --output docker-release.gpg https://download.docker.com/linux/centos/gpg
gpg --show-keys --fingerprint docker-release.gpg
# 必须人工核对完整指纹为 060A 61C5 1B55 8A7F 742B 77AA C52F EB6B 621E 9F35；不符则停止
sudo rpm --import docker-release.gpg

# 阿里云官方 Alibaba Cloud Linux 3 路径；ECS 内网镜像源
sudo wget -O /etc/yum.repos.d/docker-ce.repo http://mirrors.cloud.aliyuncs.com/docker-ce/linux/centos/docker-ce.repo
sudo sed -i 's|https://mirrors.aliyun.com|http://mirrors.cloud.aliyuncs.com|g' /etc/yum.repos.d/docker-ce.repo

# 不使用 -y；显式覆盖可能存在的全局 assumeyes，人工审查事务
sudo dnf --setopt=assumeyes=False install dnf-plugin-releasever-adapter --repo alinux3-plus
sudo dnf --setopt=assumeyes=False install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 分开执行并核对结果；启用开机启动也是管理员决定
sudo systemctl start docker
sudo systemctl enable docker

# 只读记录实际安装结果，不运行 hello-world、不新增测试容器
docker --version
docker compose version
docker buildx version
rpm -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin dnf-plugin-releasever-adapter
```

Docker key 必须先经 HTTPS 下载、完整指纹核验、显式导入，再允许包事务；`--setopt=assumeyes=False` 防止全局配置静默自动同意。若出现其他未知 key 提示，必须独立核验其官方指纹，否则拒绝；不得改回 `dnf -y`。仓库配置通过阿里云官方内网镜像取得，RPM 仍验签，不是把远端脚本直接送入 shell。

本清单不包含 `usermod -aG docker`：Docker 组等价于高权限主机控制边界。安装后由管理员决定亲自执行部署还是另行授权 `dev` 访问 daemon；预检只检查当前用户能否访问，不自行改组或每次自动加 sudo。防火墙、安全组、sshd、swap 和其他系统服务均不在本包修改范围内。

## 3. 精确源码与镜像交付

### 3.1 在已核验的本地 M9 环境制作交付物（以后执行）

在精确 `a1ce4ca` checkout 中重新生成源码 context，不使用旧缓存或未提交工作树文件：

```sh
python3 deploy/prepare_integration.py \
  --resource-commit faa5f0330ad54bd9f4d02bb498ea305651c95ed9 \
  --access-commit 0e5fed78841f8acad31278a3e06cb08b0e6e93d0
# 将输出的新 integration-* 绝对路径记为 CONTEXT，再复制本包；不得携带运行材料
mkdir -p "$CONTEXT/docs"
cp -a deploy/remote "$CONTEXT/deploy/"
cp docs/REMOTE_TRIAL.md "$CONTEXT/docs/"
test ! -e "$CONTEXT/deploy/remote/.runtime"

# 不改 M9 工具；在本打包步骤把 Windows CRLF/Linux LF 统一为 LF
python3 -c 'from pathlib import Path; import sys; p=Path(sys.argv[1]); p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))' \
  "$CONTEXT/source-manifest.json"
sha256sum "$CONTEXT/source-manifest.json"
# 规范化 LF 后必须为 e4877bea2686eff52e8708751492e4a5ae5fc1cf8bd8c3de3e6951684df5b374

# 两件交付物放入同一全新 staging，清单只记录相对 basename
STAGING="$PWD/crm-trial-c010400-delivery"
test ! -e "$STAGING"
mkdir "$STAGING"
# 以下 inspect/save 仅在已授权的本地镜像导出环境执行；远端 load/inspect 统一走 trial.sh 模式
docker image inspect sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705
docker save sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705 \
  > "$STAGING/crm-c010400-image.tar"
tar -C "$CONTEXT" -cf "$STAGING/crm-trial-c010400-source-and-tools.tar" \
  apps deploy docs source-manifest.json
(
  cd "$STAGING"
  sha256sum crm-trial-c010400-source-and-tools.tar crm-c010400-image.tar > DELIVERY_SHA256SUMS
)
```

`prepare_integration.py` 的 53 文件 allowlist 和逐 blob SHA 是源码交付依据；`deploy/remote/SOURCE_SHA256SUMS` 是同一清单的 `sha256sum` 形式。`source-manifest.json` 必须按上述打包步骤规范化为 LF 并匹配固定摘要，Windows CRLF 与 Linux LF 不再导致平台歧义。两件交付物在同一 staging 生成只含相对 basename 的清单，复制整个 staging 后直接在另一目录运行同一 `sha256sum -c`，不重建或改写可信摘要。镜像不提交 Git；只在授权的本地 Docker 环境导出。`docker save` tar 的 SHA 每轮写入 `DELIVERY_SHA256SUMS`，不能用镜像 ID 代替传输文件摘要，也不能把镜像大小当成 tar 完整性证明。传输仍须另行授权，使用已核验主机身份的 `scp`/SFTP，不粘贴私钥或密码到命令行。

### 3.2 远端核验（以后执行）

先在已核验交付目录提取独立预检材料，在目标目录仍不存在时运行预检，再把完整包解包到 `~/crm-trial`。`preflight.sh` 必须连同其同目录依赖 `docker.sh` 一起提取，不能只复制单个脚本。

```sh
# 在交付文件所在目录核对传输完整性并保存绝对路径；摘要不重建
DELIVERY_DIR=$(pwd -P)
sha256sum -c DELIVERY_SHA256SUMS

# 从同一个已核验 tar 提取两文件到独立非目标目录
PREFLIGHT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/crm-trial-preflight.XXXXXX")
tar -xf crm-trial-c010400-source-and-tools.tar -C "$PREFLIGHT_DIR" \
  deploy/remote/preflight.sh deploy/remote/docker.sh
sh "$PREFLIGHT_DIR/deploy/remote/preflight.sh"
# PREFLIGHT READY 才继续；任何同名目录/卷/网络/容器或 8088 占用都停止，不覆盖

mkdir "$HOME/crm-trial"
tar -xf crm-trial-c010400-source-and-tools.tar -C "$HOME/crm-trial"
cd "$HOME/crm-trial"
sh deploy/remote/trial.sh verify-source
sh deploy/remote/trial.sh load-image "$DELIVERY_DIR/crm-c010400-image.tar"

# 唯一一次初始化；先确认原生 Linux 权限，再做镜像/Compose 检查
sh deploy/remote/trial.sh init-env
stat -c '%a %n' deploy/remote/.runtime/.env deploy/remote/.runtime/image.env
# 两个文件必须为 600；不要 cat、打印或复制其中的密码
sh deploy/remote/trial.sh check
```

`load-image` 在任何 daemon 调用前要求 tar SHA 精确等于上表固定值。`check` 核验 Compose、锁所指精确 ID、linux/amd64、三个 revision label 和 `image-rootfs-layers.txt` 中全部 diff_ids，不启动容器，也不证明应用健康。新 `init-env` 默认写经典 store config 锁；已有 containerd index 锁只在实际 index 及全部内容断言匹配时接受。两种身份不会互相静默 fallback，禁止浮动 tag、旧 `36a89c9b` 故障镜像或缺任一扩展的镜像。

### 已部署旧树的工具更新与锁迁移（M15 专用）

若远端已按 240b9a8 执行过 `init-env`，`image.env` 恰好为 `CRM_IMAGE=cae67cc3…`，且经典 store 已加载 `129b0357…`，**不要**重新 `init-env`、重生成 `.env` 或再次 `load-image`。旧 `trial.sh` 没有新迁移函数，必须先由单一操作者完成以下整组工具更新。

在精确已审 tip 的干净 checkout 制作无 runtime 白名单包（完整提交由 tower/独审交接，不使用浮动分支名）：

```sh
UPDATE_COMMIT=<独审确认的完整40位提交>
test "$(git rev-parse "$UPDATE_COMMIT^{commit}")" = "$UPDATE_COMMIT"
test -z "$(git status --porcelain)"
UPDATE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/c010400-tools-update.XXXXXX")
git archive --format=tar --output="$UPDATE_DIR/crm-c010400-tools-update.tar" "$UPDATE_COMMIT" -- \
  deploy/remote/.gitattributes deploy/remote/.gitignore \
  deploy/remote/SOURCE_SHA256SUMS deploy/remote/apply-tools-update.sh \
  deploy/remote/compose.yml deploy/remote/docker.sh \
  deploy/remote/image-rootfs-layers.txt deploy/remote/preflight.sh \
  deploy/remote/release.env deploy/remote/trial.sh \
  deploy/remote/update-from-240b9a8.sha256 deploy/remote/verify_backup.py \
  deploy/remote/verify_image_archive.py docs/REMOTE_TRIAL.md
(
  cd "$UPDATE_DIR"
  sha256sum crm-c010400-tools-update.tar > crm-c010400-tools-update.sha256
)
```

将 tar 和原始 `.sha256` 一并交付到另一目录，先核验再解包。以下操作以 `dev` 运行，Docker 模式沿用 `CRM_TRIAL_DOCKER_SUDO=1`，不执行整个脚本 sudo：

```sh
cd /已核验交付目录
sha256sum -c crm-c010400-tools-update.sha256
UPDATE_STAGING=$(mktemp -d "${TMPDIR:-/tmp}/c010400-update-staging.XXXXXX")
tar -xf crm-c010400-tools-update.tar -C "$UPDATE_STAGING"
sh "$UPDATE_STAGING/deploy/remote/apply-tools-update.sh" \
  "$PWD/crm-c010400-tools-update.tar" \
  "$(awk '{print $1}' crm-c010400-tools-update.sha256)" \
  "$HOME/crm-trial"
```

`apply-tools-update.sh` 再独立核验 tar SHA、精确白名单和新层清单，要求现有工具与 240b9a8 哈希全一致，并把旧工具保留到 `deploy/remote.pre-c010400-update`。它只逐文件更新上述工具/文档并整组复核；**不复制、移动或删除 `.runtime`，不触碰 app、站点、容器或卷**。错误包、旧树异值、备份冲突、更新失败/中断或整组不一致均不得继续；保留现场和旧工具副本，停止并交 tower 处理，不能把部分更新当成就绪。只有脚本返回整组 `PASS` 才执行：

```sh
cd "$HOME/crm-trial"
sh deploy/remote/trial.sh migrate-image-lock-to-config --confirm-classic-image-lock-migration
stat -c '%a %n' deploy/remote/.runtime/.env deploy/remote/.runtime/image.env \
  deploy/remote/.runtime/image.env.pre-c010400-config
sh deploy/remote/trial.sh check
```

锁迁移只接受精确旧 index 锁，先验证 config 的 ID、平台、labels 和完整 RootFS，再要求旧锁为非 symlink 的 0600 文件；它排他保留旧锁到 `image.env.pre-c010400-config`，在同目录原子更换新锁，不改 `.env`、站点、容器或卷。已有备份/临时路径、错误旧值、错误 config/平台/labels/diff_ids 均拒绝且不换锁。两个动作都只服务本次 M15 停点，不是通用升级器或任意 ID 回退。

### 运行站点的已审补丁镜像更新（待 M9 元数据）

现有工具支持上述工具更新和旧锁迁移，但运行站点补丁还必须有 M9 提供的独立 `release.env`、完整 `image-rootfs-layers.txt` 和镜像 tar。元数据须包含精确 `CRM_IMAGE_CONFIG`、OCI index、平台 manifest、tar SHA 及三个源码 revision；本包不猜补丁 digest、不重 build。当前锁须为旧 config `129b0357…`，且站点已完成双迁移。

从独立已审 staging 调用新工具，显式复用现有 runtime，不覆盖旧工具目录：

```sh
CRM_TRIAL_RUNTIME_DIR="$HOME/crm-trial/deploy/remote/.runtime" \
  sh "$UPDATE_STAGING/deploy/remote/trial.sh" update-site-image \
  /已审release目录 /已核验镜像.tar --confirm-site-image-update
```

该动作先离线核验 tar SHA、index→amd64 manifest→config 及逐层 diff_ids，再完成四件备份可读检查后加载并验证新镜像，保留 `.env`、站点配置、数据库/卷、原镜像和 `image.env.pre-site-update`，以 Compose 原生重建。六个长驻应用服务须全部运行新 config，configurator 须同 config 且 exit 0；DB/Redis 容器 ID、`.env` 和站点配置哈希不得改变。全部目标、备份和临时路径冲突在运行态变化前预检，完整元数据先写入临时文件。切换后任何退出、写入/rename失败或可捕获信号都会先独立尽力 `compose stop`，再分别尝试锁恢复和元数据隔离，并把 stop/lock/metadata 结果写入 `site-update.state`；任何失败均不自动重启已知权限缺陷版本。成功后才提交新 manifest/层清单供后续 `check`。后续权限复验失败同样立即停写/维护，不以旧版回退冒充健康。不 `down -v`/prune、不 init、不重复旧 load 迁移、不改公开范围/SSH/firewall，也不解除 M8/M9 门禁。

维护/恢复入口不依赖新元数据有效。每条命令都独立使用**同一已审 staging 脚本和原 runtime 绝对路径**，不覆盖旧工具，也不继承前一条命令的局部变量：

```sh
CRM_TRIAL_RUNTIME_DIR="$HOME/crm-trial/deploy/remote/.runtime" \
  sh "$UPDATE_STAGING/deploy/remote/trial.sh" maintenance-status
CRM_TRIAL_RUNTIME_DIR="$HOME/crm-trial/deploy/remote/.runtime" \
  sh "$UPDATE_STAGING/deploy/remote/trial.sh" maintenance-stop
# 仅在已审查决定恢复旧锁时：
CRM_TRIAL_RUNTIME_DIR="$HOME/crm-trial/deploy/remote/.runtime" \
  sh "$UPDATE_STAGING/deploy/remote/trial.sh" restore-old-lock --confirm-site-image-update
# 状态一致后才复核，不直接调用旧树脚本：
CRM_TRIAL_RUNTIME_DIR="$HOME/crm-trial/deploy/remote/.runtime" \
  sh "$UPDATE_STAGING/deploy/remote/trial.sh" check
```

`stop` 同样不先验证 release/layers。SIGKILL 无法捕获，本包不声称可 trap；遗留 `updating` 状态即表示中断，先按维护入口检查，不得把进程消失当成已停稳。

## 4. 新站点、备份、安装与双迁移

确认操作员已审查“只放合成数据”，且上面的 init-env/stat/check 已成功后，依次执行；每步失败都停止，保留现场，不盲目重跑：

```sh
cd "$HOME/crm-trial"
sh deploy/remote/trial.sh create-site --confirm-synthetic-only
sh deploy/remote/trial.sh up
sh deploy/remote/trial.sh backup
sh deploy/remote/trial.sh install-extensions --confirm-synthetic-only
sh deploy/remote/trial.sh migrate
sh deploy/remote/trial.sh versions
```

关键语义：

- `init-env` 只在第 3.2 节执行一次，于独立 runtime 中生成新随机密码，O_EXCL/防覆盖；不会读取本地凭据。
- `create-site` 再次执行只读资源冲突检查，并要求显式确认。它只由 `bench new-site --install-app crm` 安装 CRM，同时把合成声明、初始禁用导入、禁 Server Script 和禁邮件写入新站配置；**不会自动安装四个 app**。
- 第一次 `backup` 必须发生在扩展安装前。`backup` 使用原生 `bench backup --with-files`，并完整读取当次新数据库 gzip、公/私文件 tar 和站点配置；只输出 backup stem，不输出配置正文。只有该命令及其完整性检查均返回 0 才能继续。脚本不写 backup 成功标记，`install-extensions` 也不读取备份标记，因此“先备份”是操作员必须执行的顺序门禁，**不是机器强制保证**；备份存在不等于恢复成功。
- `install-extensions` 依次执行 `install-app resource_import`、`install-app team_access`；`migrate` 明确执行两次完整 `bench migrate` 后 `clear-cache`。任一失败不自动卸载、不删字段、不重复初始化。
- 最终 `versions` 的镜像版本应包含四个 app，`frappe.get_installed_apps` 应只包含 `frappe`、`crm`、`resource_import`、`team_access`。数量/版本正确仍不等于权限通过。

## 5. 首次 HTTP 安全基线

在任何业务烟测或导入前，按 M9 既有门槛完成：

1. Administrator 打开 `/app/system-settings`，记录 **Show Full Error and Allow Reporting of Issues to the Developer** 原值并设为 0，正常 Save 后 `clear-cache`。不要用同名 site_config 键代替。
2. 明确选择本新站语言和时区，并按合成试用隐私基线关闭 telemetry。新站若因缺失必填项无法保存，停止并协调定点初始化；不得用 `ignore_mandatory`、SQL、改 DOM/DocField 或随意猜时区作为默认捷径。
3. 新站初始 `resource_import_disabled=1`。只有上述设置和匿名/会话异常负测完成后，才执行 `sh deploy/remote/trial.sh enable-import --confirm-synthetic-only`；入口仍仅 System Manager/Administrator，不开放给普通 Sales User。
4. 若登录资产异常，保留证据并核对 M9 的精确共享 `assets_json` 缓存处理；禁止 `FLUSHDB`、通配清缓存或注入 sid/DOM 绕过登录。

## 6. 后续逐关验收（当前全部未执行）

### G1：安装、双迁移与健康

- `trial.sh check`、`up`、`versions` 全部返回 0，四 app 集合与固定版本一致。
- 两次 migrate 均有真实成功日志；`docker compose ps` 中 9 个长驻服务保持运行，DB healthy。
- `curl -sS -H 'Host: crm.localhost' http://127.0.0.1:8088/api/method/ping` 返回 `pong`。
- 观察内存、OOM 和重启计数；不能用一次 HTTP 200 声称 1.8 GiB 稳定。

### G2：标准登录与资产

- Guest `/login` 引用带 hash 的 Framework JS/CSS，全部 200 且 Content-Type 正确；再用真实表单登录 Administrator，核对会话身份和 `/crm`。
- 不用 API 登录代替标准网页登录，不用修改 DOM、注入 Cookie 或临时快捷方式冒充通过。
- 完成 System Settings 基线和 CRM 原生 setup 选择；不接邮箱、不生成示例、不邀请真实人员。

### G3：双用户基础权限（不等于 M8 全矩阵）

只创建 `m13-a@example.invalid`、`m13-b@example.invalid` 两个合成 System User，角色仅 `Sales User`，各自独立高强度密码。用两个隔离浏览器上下文验证：

- A 的私有 Lead 及 Private Note：A 可读；B 的列表、直接 URL、搜索、导出均不可见，PUT 拒绝。
- 通过 Open ToDo 将另一合成 Lead 分配给 B 后，B 可读取并按授权协作；A 的 Private Note 仍不可见。
- Shared Note 对共享父记录读者只读，写权限不因父记录可读而自动获得；撤回协作/分配后立即复测。
- 另测普通 Sales User 不能打开 `/resource-import`。

完整 M8 API 回归还要求安装前准备 legacy DocShare/历史夹具及大量 R6/R7、附件、删除、实时事件和恢复用例。本全新远端流程没有执行这些前置夹具和全矩阵，G3 基础人工结果不得标成 M8 完整验收或生产门禁解除。

### G4：Windows SSH 隧道

主机指纹必须经可信通道核对，使用专用 known_hosts 和 `StrictHostKeyChecking=yes`；不得自动接受未知密钥。若交付包含 M12，优先按 `docs/WINDOWS_CLIENT.md` 使用 `deploy/windows/start-tunnel.ps1 -WhatIf` 后再启动，等价固定参数为：

```powershell
ssh -N -T `
  -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes `
  -o IdentitiesOnly=yes -o PreferredAuthentications=publickey `
  -o UserKnownHostsFile="<已核验的专用known_hosts路径>" `
  -i "<私钥路径>" `
  -L 127.0.0.1:18088:127.0.0.1:8088 dev@8.133.190.46
```

隧道保持前台运行，另开窗口核对 `http://127.0.0.1:18088/login` 和 `/crm`。SSH 建立只证明转发，不证明 CRM 健康；不得改成公网 IP 直接访问或放开服务器 8088。

### G5：PWA 资产与 Edge 安装

- 在同一 `http://127.0.0.1:18088` origin 检查 `/crm` 引用的实际 manifest、Service Worker、JS/CSS 图标响应、MIME 和作用范围；路径以页面真实声明为准，不猜一个 manifest URL。
- Edge「将此站点作为应用安装」后，`edge://apps` 有卡片、独立窗口可启动，正常表单登录和双用户界面可操作。
- 验证断隧道负例、重连、强制刷新和卸载；不承诺离线、原生 exe/MSIX、开机自启或移动实机体验。

### G6：停止且保留资源

验收或故障暂停前再备份，然后只停止本项目：

```sh
cd "$HOME/crm-trial"
sh deploy/remote/trial.sh backup
sh deploy/remote/trial.sh stop
sh deploy/remote/trial.sh status
sh deploy/remote/trial.sh inspect-volumes
```

`stop` 不删容器、镜像、网络、卷或备份。不得执行 `down -v`、`prune`、`uninstall-app`、删 Custom Field 或覆盖现库。恢复仍须按 M9 在同版本、独立项目/卷中进行真实 restore 和权限验收，不能把 backup readability check 当恢复通过。

## 7. 执行状态台账

| 门槛 | 当前状态 |
|---|---|
| 官方安装来源与管理员命令核对 | 已核文档；未执行安装/sudo/systemctl |
| 远端只读预检 | 未执行；脚本仅本地语法/受控行为检查 |
| 源码/镜像实际导出、传输、加载 | 未执行；只固定 ID、来源和核验方案 |
| 新目录/项目/卷/回环站点 | 未创建 |
| 首次备份、双扩展安装、两次 migrate | 未执行 |
| Administrator 标准登录和系统基线 | 未执行 |
| 双用户基础权限 / M8 完整矩阵 | 均未执行 |
| Windows 隧道和 Edge PWA | 未执行 |
| 停止保留与同版本恢复 | 未执行；只提供保留式命令 |

## 8. 本轮本地验证证据（不代替远端验收）

- `bash -n deploy/remote/preflight.sh deploy/remote/trial.sh`、Python AST 和 `git diff --check` 通过。
- 第一 Ubuntu 的既有 Docker Compose 只做 `config` 渲染，未连接 daemon 创建资源：11 个服务（含 setup profile）、仅 frontend 发布 `127.0.0.1:8088`、4 个固定独立卷、backend 1 worker、未确认时合成标记为 `not-confirmed`，断言通过。
- 53 个 app/build 源文件与 M9 `source-manifest.json` 全部一致；在合成副本中篡改 `team_access/install.py` 后 `verify-source` 拒绝。
- `init-env` 防覆盖、三个显式合成确认拒绝路径及阶段顺序门禁通过；mock Docker 完整演练确认 create-site → up → 两个 install-app → 恰好两次 migrate → clear-cache → enable-import，重复 create/migrate 拒绝。mock 只验证编排，不是真实安装证据。
- 合成四件备份夹具通过 gzip/tar/config 完整性验证；stub 预检在本地非 Alibaba OS 上明确失败且未创建目标目录。
- R1 修复后，Windows CRLF 输入与 Linux LF 输入均按制作步骤规范化为同一 LF manifest，SHA-256 固定为 `e4877bea2686eff52e8708751492e4a5ae5fc1cf8bd8c3de3e6951684df5b374`；指南中 init-env 仅出现一次，顺序静态断言为 init-env → stat → check → create-site。
- R1 在第一 Ubuntu 原生 `/tmp` 隔离副本验证：交付 preflight 为 100644、未对包执行 chmod，内部显式 `sh` 调用无 Permission denied；脚本无 CRLF，runtime 为 0700、两个文件为 0600；只含相对 basename 的交付清单复制到另一目录后两件文件均 `sha256sum -c` OK。检查前后 Docker 服务均为 `activating`，状态未变；未调用真实 Docker daemon、未连接远端、未触碰第二发行版。原生远端权限仍必须按第 3.2 节 `stat` 验收。

因此当前交付只能称为“可审查、可本地做静态/受控验证的远端试用部署材料”，不能称为服务端已上线、Windows 已安装试用或生产可用。
