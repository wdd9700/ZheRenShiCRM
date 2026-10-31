# 远端 Docker Engine 与 Compose 安装证据（C010500）

**状态：已在本轮真实执行安装并启动 `docker` 服务；镜像拉取、业务容器、CRM 部署与任何验收均未进行。**

本文件只覆盖 M14 的授权范围：在 `dev@8.133.190.46` 上安装 Docker Engine、Compose 插件及必要依赖，并验证 sudo daemon 访问。它**不是**生产批准，也不替代 M8/M9 的权限与恢复验收，更不构成 `docs/REMOTE_TRIAL.md` 中试用部署流程的完成记录。所有命令均为本轮实际执行所得，未执行项在 §10 明列。

## 1. 授权与范围

用户明确授权在该服务器上使用 sudo 安装 Docker 和 Compose，用于调试、部署及实际测试。据此本轮的范围边界为：

| 允许 | 禁止（本轮未做） |
|---|---|
| 配置 Docker 官方仓库、导入经完整指纹核验的官方 key | 关闭 TLS 校验、`gpgcheck=0`、跳过验签 |
| 安装 `docker-ce`/`docker-ce-cli`/`containerd.io`/`docker-buildx-plugin`/`docker-compose-plugin` 及依赖 | 卸载、替换或降级任何既有软件包 |
| `systemctl start docker` | `systemctl enable docker`（不设开机自启） |
| 只读版本与 daemon 访问验证 | 拉取镜像、运行 `hello-world`、创建任何容器 |
| 记录 Docker 自身网络的运行影响 | 改防火墙/安全组/sshd/swap、`usermod -aG docker`、停其他服务、付费扩容、升级系统 Python |

`dev` 未被加入 `docker` 组，Docker daemon 只通过显式 `sudo` 访问；后续部署调用方式见 §11。

## 2. 身份、凭据与连接边界

全程使用 Git Bash 的 `/usr/bin/ssh`，连接参数固定为：

```sh
-i <session 附件中的 dev_8.133.190.46_id_ed25519>   # 仅作为 -i 参数
-o UserKnownHostsFile=P:/CRM/.tower/worktrees/wt-10/deploy/.runtime/m10-known_hosts
-o StrictHostKeyChecking=yes
-o IdentitiesOnly=yes
-o BatchMode=yes
```

- 私钥正文**未被读取、打印、复制或提交**；仅作为 `-i` 参数传给 `ssh`。
- `BatchMode=yes` 保证不会出现交互式口令回退；`IdentitiesOnly=yes` 保证只使用指定身份。
- 主机身份取自 M10 遗留的专用 known_hosts，本轮重新计算其指纹：

```
$ ssh-keygen -lf <m10-known_hosts>
256 SHA256:JHFV75F2oc1tYqjd4viv130aknkd7fOwtKEpmGtgy80 8.133.190.46 (ED25519)
```

指纹与 M10 记录的 `SHA256:JHFV75F2oc1tYqjd4viv130aknkd7fOwtKEpmGtgy80` 逐字符一致，且 `StrictHostKeyChecking=yes` 下连接成功，说明 hosts 文件中的 key 就是实际出示的 key。**该指纹仍是 TOFU 记录，未做带外认证**；若日后变化必须停止，不接受新 key。

SSH 客户端为 `OpenSSH_10.2p1`，连接时会打印 "connection is not using a post-quantum key exchange algorithm" 警告。该警告说明本次会话的密钥交换不含 PQ 算法，不影响主机身份校验结论；本轮未修改服务器 sshd 配置。

## 3. 安装前只读预检

先 `sudo -n true` 验证免交互提权，不猜密码；确认在无密码提示的前提下才继续。实际环境与 M13 指南假设的差异见 §12。

| 项 | 实测值 |
|---|---|
| OS | Alibaba Cloud Linux 3 (OpenAnolis Edition)，`alinux-release-3.2104.13.3-1.al8` |
| 内核 | `5.10.134-19.8.al8.x86_64` |
| CPU / 内存 | 2 vCPU / 1870 MiB 总内存，安装前已用 280 MiB，可用 1590 MiB |
| swap | 无（`/proc/swaps` 为空），本轮未添加 |
| 磁盘 | `/dev/vda3` 40G，已用 4.5G，可用 33G（`/` 与 `/home` 同一文件系统） |
| 运行时长 | 57 天 |
| 既有容器栈 | 无 `docker`、`docker-compose`、`podman`、`containerd` 二进制；`rpm -qa` 中无任何 docker/containerd/runc/podman 包 |
| 既有目录 / unit | 无 `/etc/docker`、`/var/lib/docker`、`/var/lib/containerd`；`systemctl list-unit-files` 中无 docker unit |
| dnf 插件 | `dnf-plugin-releasever-adapter-1.0-3.al8.noarch` **已预装** |
| 既有仓库 | `AliYun.repo`、`epel*.repo`；无 `docker-ce.repo` |
| 工具链 | `curl`、`wget`、`gpg`(2.2.20)、`rpm`、`dnf`(4.7.0)、`systemctl` 均存在 |
| sudo | `sudo -n true` 成功；`sudo -n -l` 显示 `(ALL) NOPASSWD: ALL` |

因此没有触发任何"M13 指南里的卸载旧版本"步骤：机器上不存在可冲突的既有安装或数据。

安装前网络与监听基线（用于对照 §9 的实际变化）：

```
$ ip -o link show | awk '{print $2}'      # lo, eth0
$ ip -4 route
default via 172.22.159.253 dev eth0 proto dhcp src 172.22.145.7 metric 100
172.22.144.0/20 dev eth0 proto kernel scope link src 172.22.145.7 metric 100
$ sudo iptables -t filter -S | wc -l      # 3
$ sudo iptables -t nat    -S | wc -l      # 4
$ sudo iptables -t mangle -S | wc -l      # 5
$ sudo ss -lntup                          # 仅 0.0.0.0:22 sshd、127.0.0.1:323 chronyd
$ systemctl list-units --type=service --state=running --no-legend | wc -l   # 19
```

## 4. Docker 官方仓库 key 获取与指纹核验

指南要求"经 HTTPS 获取 Docker 官方 key 并人工核对完整指纹"。本轮首选的官方原始地址**不可用**：

```
$ curl --fail --location --proto '=https' --tlsv1.2 -o /dev/null https://download.docker.com/linux/centos/gpg
curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to download.docker.com:443
```

观测事实：DNS 解析到 CloudFront（`143.204.181.26/.107`），TCP 443 可建立（`/dev/tcp` 探测成功），但 TLS 握手在 ClientHello 之后被断开。这**只是本次观测到的现象**；"区域级阻断"是推断，未做进一步证明，不作为结论记录。

未采用任何削弱校验的手段（未关闭 TLS、未 `--insecure`、未 `gpg --import` 未核验文件）。改从两个**经 TLS 校验的 HTTPS 镜像**取同一份 key 并交叉比对：

```sh
umask 077
cd "$HOME/c010500-docker-install"
curl --fail --location --proto '=https' --tlsv1.2 -sS \
  --output docker-release.aliyun.gpg https://mirrors.aliyun.com/docker-ce/linux/centos/gpg
curl --fail --location --proto '=https' --tlsv1.2 -sS \
  --output docker-release.tuna.gpg   https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/centos/gpg
sha256sum docker-release.aliyun.gpg docker-release.tuna.gpg
cmp -s docker-release.aliyun.gpg docker-release.tuna.gpg
gpg --show-keys --fingerprint --with-subkey-fingerprint docker-release.aliyun.gpg
```

结果：

```
e6c650e0700b1bf4868b693b30761b926844befc8a0acb7ac0dd9b1faf1b7423  docker-release.aliyun.gpg
e6c650e0700b1bf4868b693b30761b926844befc8a0acb7ac0dd9b1faf1b7423  docker-release.tuna.gpg
IDENTICAL
pub   rsa4096 2017-02-22 [SCEA]
      060A 61C5 1B55 8A7F 742B  77AA C52F EB6B 621E 9F35
uid                      Docker Release (CE rpm) <docker@docker.com>
```

完整指纹 `060A61C51B558A7F742B77AAC52FEB6B621E9F35` 与 M13 已审查指南固定值逐字符一致（RSA4096，2017-02-22）。**信任锚是先前的完整指纹 pin，不是镜像来源**；镜像间 sha256 相同只是辅助证据。该替换方案已上报 tower 并获准继续（"Proceed with pinned official key through HTTPS mirror"）。

导入与核对：

```sh
sudo rpm --import "$HOME/c010500-docker-install/docker-release.aliyun.gpg"
rpm -q gpg-pubkey                     # gpg-pubkey-621e9f35-58adea78
```

Key ID `621e9f35`、时间戳 `58adea78` = 2017-02-22，与核验过的文件一致。全程没有出现其他未知 key 提示；若出现本应停下独立核验，本轮无此情况。

## 5. 仓库配置

`docker-ce.repo` 由同一 HTTPS 镜像取得（不把远端脚本管道进 shell），安装前确认 `/etc/yum.repos.d/docker-ce.repo` 不存在，不会覆盖任何既有配置：

```sh
curl --fail --location --proto '=https' --tlsv1.2 -sS \
  --output /tmp/docker-ce.repo.upstream https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
sudo install -m 0644 -o root -g root /tmp/docker-ce.repo.upstream /etc/yum.repos.d/docker-ce.repo
```

注入文件保持上游原样：`docker-ce-stable` 为唯一 `enabled=1` 的段，`test`/`nightly`/`debuginfo`/`source` 均为 `enabled=0`；每段 `gpgcheck=1`，`baseurl` 与 `gpgkey` 均为 `https://mirrors.aliyun.com/...`。未出现 `gpgcheck=0`、`repo_gpgcheck` 放宽或 `sslverify=0`。

`$releasever` 由已预装的 `dnf-plugin-releasever-adapter` 按 `/etc/yum/pluginconf.d/releasever_adapter.conf` 处理：`[releasevermapping] 3 = 8`，`[reposlist] include=docker-ce.repo, ...`。因此 Docker 仓库被解析为 CentOS 8 路径，而系统仓库仍用 alinux3 路径：

```
$ dnf repoinfo docker-ce-stable
Repo-status        : enabled
Repo-pkgs          : 252
Repo-baseurl       : https://mirrors.aliyun.com/docker-ce/linux/centos/8/x86_64/stable
Repo-filename      : /etc/yum.repos.d/docker-ce.repo
```

另注：该镜像的 `docker-ce-stable` 元数据 `Repo-updated: Thu 23 May 2024`，即镜像内容停留在 2024-05，因此可安装版本是 `docker-ce 26.1.3` 而不是更新的 27/28.x。这是可安装范围的事实限制，不影响本次安装可行性，也不作为"最新版本"宣称；见 §12。

## 6. DNF 事务审查（确认前）

按要求不使用 `-y`、不使用 `yes |` 流水线，强制 `assumeyes=False`，并先用 `--assumeno` 只审阅不提交：

```sh
sudo dnf --setopt=assumeyes=False --assumeno install \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

审查到的事务（原样摘录）：

```
Installing:
 containerd.io               x86_64  1.6.32-3.1.el8   docker-ce-stable    35 M
 docker-buildx-plugin        x86_64  0.14.0-1.el8     docker-ce-stable    14 M
 docker-ce                   x86_64  3:26.1.3-1.el8   docker-ce-stable    27 M
 docker-ce-cli               x86_64  1:26.1.3-1.el8   docker-ce-stable   7.8 M
 docker-compose-plugin       x86_64  2.27.0-1.el8     docker-ce-stable    13 M
Installing dependencies:
 fuse-overlayfs              x86_64  1.13-1.0.1.al8   alinux3-updates     70 k
 fuse3                       x86_64  3.3.0-19.1.al8   alinux3-updates     55 k
 fuse3-libs                  x86_64  3.3.0-19.1.al8   alinux3-updates     97 k
 libcgroup                   x86_64  2.0-1.0.1.al8    alinux3-updates     79 k
 libslirp                    x86_64  4.4.0-2.al8      alinux3-updates     71 k
 slirp4netns                 x86_64  1.2.3-1.al8      alinux3-updates     56 k
Installing weak dependencies:
 docker-ce-rootless-extras   x86_64  26.1.3-1.el8     docker-ce-stable   5.0 M
Transaction Summary
Install  12 Packages
Total download size: 103 M
Installed size: 390 M
Operation aborted.
```

判定：**纯增量**。没有 Removing / Upgrading / Downgrading / Replacing 段，不触及系统 Python、sshd、防火墙或其他已装包；依赖全部来自系统 `alinux3-updates` 仓库，只有 Docker 自身包来自 `docker-ce-stable`，全部需通过已导入 key 的 RPM 验签。`docker-ce-rootless-extras` 是 `docker-ce` 的 weak dependency，属于该版本的默认安装集合，本轮保留。

## 7. 真实安装执行与结果

在看清上述事务后执行同一组包，`assumeyes=False` 保持，仅提供**一次**有界的确认输入（不是无限 `yes`）：

```sh
printf 'y\n' | sudo dnf --setopt=assumeyes=False install \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

执行结果（摘录，`Complete!` 表示事务成功）：

```
  Installing       : fuse3-libs-3.3.0-19.1.al8.x86_64                       2/12 
  Installing       : docker-ce-cli-1:26.1.3-1.el8.x86_64                    6/12 
  Installing       : containerd.io-1.6.32-3.1.el8.x86_64                    7/12 
  Installing       : docker-ce-3:26.1.3-1.el8.x86_64                       11/12 
  Installing       : docker-ce-rootless-extras-26.1.3-1.el8.x86_64         12/12 
  Verifying        : docker-ce-3:26.1.3-1.el8.x86_64                        9/12 
  Verifying        : docker-compose-plugin-2.27.0-1.el8.x86_64             12/12 

Installed:
  containerd.io-1.6.32-3.1.el8.x86_64
  docker-buildx-plugin-0.14.0-1.el8.x86_64
  docker-ce-3:26.1.3-1.el8.x86_64
  docker-ce-cli-1:26.1.3-1.el8.x86_64
  docker-ce-rootless-extras-26.1.3-1.el8.x86_64
  docker-compose-plugin-2.27.0-1.el8.x86_64
  fuse-overlayfs-1.13-1.0.1.al8.x86_64
  fuse3-3.3.0-19.1.al8.x86_64
  fuse3-libs-3.3.0-19.1.al8.x86_64
  libcgroup-2.0-1.0.1.al8.x86_64
  libslirp-4.4.0-2.al8.x86_64
  slirp4netns-1.2.3-1.al8.x86_64
Complete!
```

安装后 `rpm -q` 全部命中：

```
docker-ce-26.1.3-1.el8.x86_64
docker-ce-cli-26.1.3-1.el8.x86_64
containerd.io-1.6.32-3.1.el8.x86_64
docker-buildx-plugin-0.14.0-1.el8.x86_64
docker-compose-plugin-2.27.0-1.el8.x86_64
docker-ce-rootless-extras-26.1.3-1.el8.x86_64
```

最终 12 个包的 `Verifying` 阶段全部通过（RPM 签名由已导入的 `gpg-pubkey-621e9f35-58adea78` 验签），全部为 `Installing`，没有一条 `Removing`/`Upgrading`/`Replacing`/`Obsoleting`。

DNF 事务历史只有一条记录，与预览一致：

```
ID | Command line                    | Date and time     | Action(s) | Altered
 1 | --setopt=assumeyes=False        | 2026-10-31 22:30  | Install   |   12
```

说明：该命令的 shell 管道退出码来自末尾的 `tail`，因此本报告**不以管道退出码**作为成功证据，而以 `Complete!`、`rpm -q` 全量命中与 `dnf history` 的单一 12 包事务三项一致证据为准。

## 8. 服务启动与版本验证

按要求只 `start`、不 `enable`，未创建任何容器：

```sh
sudo systemctl start docker     # exit 0
systemctl is-active docker      # active
systemctl is-enabled docker     # disabled
systemctl is-enabled containerd # disabled
sudo ls -l /var/run/docker.sock # srw-rw---- 1 root docker
```

实际版本（`sudo` 下访问 daemon）：

```
$ sudo docker --version
Docker version 26.1.3, build b72abbb
$ sudo docker compose version
Docker Compose version v2.27.0
$ sudo docker buildx version
github.com/docker/buildx v0.14.0 171fcbe
$ sudo docker version --format '{{.Client.Version}} / {{.Server.Version}} ({{.Server.Os}}/{{.Server.Arch}})'
26.1.3 / 26.1.3 (linux/amd64)
```

`sudo docker info` 关键字段：

```
Server Version: 26.1.3
Storage Driver: overlay2
Cgroup Driver: cgroupfs   Cgroup Version: 1
Kernel Version: 5.10.134-19.8.al8.x86_64
Operating System: Alibaba Cloud Linux 3.2104 U13.3 (OpenAnolis Edition)
CPUs: 2   Total Memory: 1.827GiB
Docker Root Dir: /var/lib/docker
Containers: 0   Images: 0
```

即 Engine 与 Compose 插件都真实可用，daemon 通过 `sudo` 可访问且已实际应答（`Server Version` 来自 daemon 而非客户端），但没有拉取任何镜像、没有运行 `hello-world`、没有业务容器。

**非提权访问被拒绝**（证明 `dev` 未被授予 daemon 权限）：

```
$ docker info            # 无 sudo
exit=1
ERROR: permission denied while trying to connect to the Docker daemon socket at
unix:///var/run/docker.sock: ... connect: permission denied
$ id dev
uid=1000(dev) gid=1000(dev) groups=1000(dev),10(wheel)
```

资源池：`Containers: 0`、`Images: 0`、`Volumes: 0`，网络只有默认 `bridge`/`host`/`none`，没有任何自定义网络或 Compose 项目。

## 9. 系统实际变化清单

| 项 | 安装前 | 安装后 |
|---|---|---|
| RPM 包 | 无 docker/containerd | 新增 12 个包（§7 列表） |
| `/etc/yum.repos.d/docker-ce.repo` | 不存在 | 存在，`root:root 0644`，仅 `docker-ce-stable` 启用 |
| rpm 信任库 | 无 Docker key | 新增 `gpg-pubkey-621e9f35-58adea78` |
| `/etc/docker/` | 不存在 | 存在且**为空**（无 `daemon.json`，全部默认配置） |
| `/var/lib/docker/` | 不存在 | 存在，`overlay2` 根目录 |
| systemd 单元 | 无 docker unit | `docker.service`、`containerd.service`，均 `active` / `disabled` |
| 新增系统组 | — | `docker` 组被创建（`dev` 不在其中） |
| 网络接口 | `lo`、`eth0` | 新增 `docker0`，`172.17.0.1/16`，`<NO-CARRIER,state DOWN>` |
| 路由表 | 默认路由 + `172.22.144.0/20` | 新增 `172.17.0.0/16 dev docker0` |
| iptables 规则数 | filter 3 / nat 4 / mangle 5 | filter 18 / nat 9 / mangle 5 |
| iptables 链 | 无 DOCKER 链 | 新增 `DOCKER` 链与 `-A POSTROUTING -s 172.17.0.0/16 ! -o docker0 -j MASQUERADE` |
| `net.ipv4.ip_forward` | 未采集基线 | 当前为 `1` |
| 监听端口 | 22/tcp sshd、127.0.0.1:323 chronyd | **不变**，Docker 未新增对外监听端口 |
| 运行中的 service 数 | 19 | 22（其中可见新增项为 `docker.service`、`containerd.service`） |
| 磁盘 | `/` 已用 4.5G，可用 33G | `/` 已用 5.1G，可用 33G（+0.6G） |
| 内存 | used 280 MiB | used 340 MiB（dnf 缓存计入 buff/cache 后回落，available 1530 MiB） |
| dnf 事务历史 | — | 1 条，Install 12 |
| 审计暂存目录 | — | `/home/dev/c010500-docker-install/`（两个 key 文件副本，`0600`，仅公钥） |

Docker 的桥接、iptables MASQUERADE 与转发开关属于 Docker 正常运行时行为（未写入任何 sysctl drop-in 文件，`rpm -ql docker-ce containerd.io` 中无 `.conf`/sysctl 文件）。由于安装前未采集 `ip_forward` 基线，**不宣称该项由本次安装从 0 改为 1**，只记录现状。

运行中的 service 总数 19→22 与"可点名的新增单元只有 2 个"存在 1 个差额：安装前只采集了数量、未采集单元名清单，差额无法归因，此处如实保留不作推断。

## 10. 明确未执行 / 未改变项

- **未 `systemctl enable`**：`docker.service` 与 `containerd.service` 均为 `disabled`，重启后不会自启。
- **未改组**：`dev` 仍在 `wheel`，不在 `docker` 组；未执行 `usermod -aG docker`。
- **未拉镜像**：`Images: 0`；未拉 `hello-world`，未导入 M13 候选镜像。
- **未建容器/卷/项目网络**：`Containers: 0`、`Volumes: 0`，网络只剩默认三项。
- **未部署 CRM**：未跑 `deploy/remote/trial.sh`（M13 分支），未创建 `~/crm-trial`、`crm-trial-c010400` Compose 项目，未监听 `127.0.0.1:8088`。
- **未改基础设施**：防火墙/安全组、`sshd`、swap、`resolv.conf` 均未改动；未停任何既有服务；未扩容。
- **未卸载或替换任何既有包**：本次事务纯增量；系统 Python 3.6.8 未动、未另装解释器。
- **未执行 M8/M9 工作**：M8 仍 blocked、M9 仍 active，其验收不因本次安装推进。
- **未验证容量**：M13 栈（9 个长驻服务、约 1.5 GB 镜像层）在 2 vCPU / 1.8 GiB / 无 swap 上是否可稳定运行，本轮完全没有测试；`docker0` 已创建但未经任何容器流量验证。

## 11. 后续部署调用方式

`dev` 没有 daemon 权限，因此后续所有 Docker 调用必须显式带 `sudo`，不要依赖 shell alias 或 `docker` 组：

```sh
# 一次性导入候选镜像（M13 §3.1 产出的 tar），再按精确 ID 校验
sudo docker load -i ~/delivery/crm-c010400-image.tar
sudo docker image inspect sha256:cae67cc3ad2bfebffd3635efd7ffd4741528bbc1ad29d84a92589df7d3ba0705

# 预检 / 运维入口（M13 deploy/remote/），逐条显式 sudo
sudo docker compose version
sudo docker version --format '{{.Server.Version}}'
sudo docker ps -a

# 启动隔离试用栈（示例形态，参数以 M13 release.env 为准）
sudo docker compose -p crm-trial-c010400 \
  --env-file ./release.env --env-file ./image.env \
  -f ./compose.yml up -d

# 只读状态
sudo docker compose -p crm-trial-c010400 ps -a
```

由于 Docker 监听在 `127.0.0.1:8088`（M13 设计），外部访问仍需 Windows 侧 SSH 隧道，本轮未建立也未验证。

**需主控决策的适配点（本轮只报告，未修改 M13）**：`deploy/remote/trial.sh:50-53` 的 `require_docker` 直接以当前用户调用 `docker`/`docker compose`，并在"current user cannot access the local Docker daemon"时 `fail`；`preflight.sh:77-115` 同样以非 sudo 方式调用。因此在不给 `dev` 加 `docker` 组的前提下，这两个脚本会在此检查处失败。可选方向（均未执行，需授权）：

1. 以 root 身份运行脚本（`sudo` 下 `HOME` 会变化，`~/crm-trial` 路径语义随之改变，需要显式传目录参数）；
2. 在脚本内把所有 `docker` 调用改为显式 `sudo docker`（需要独立审查的代码改动）；
3. 由用户决定是否另行授权 `dev` 加入 `docker` 组——这等价于授予高权限主机控制，本轮明确未做。

## 12. 阻碍、偏差与复评点

1. **官方源不可达（观测）**：`download.docker.com:443` TCP 可连、TLS 握手被对端断开（`SSL_ERROR_SYSCALL`），DNS 指向 CloudFront。仅记录现象，不把"区域级阻断"写成已证实原因。
2. **key 来源偏差（已获批）**：改用 `https://mirrors.aliyun.com` 与 `https://mirrors.tuna.tsinghua.edu.cn` 两个 HTTPS 镜像取同一份 key，`sha256` 相同且字节一致，完整指纹与 M13 指南固定值一致；tower 已确认"信任依据为先前独立固定指纹，镜像间相同 SHA 仅为辅助证据"。未关闭 TLS、未跳过导入前核验。
3. **内网镜像端点无有效 TLS 证书**：`https://mirrors.cloud.aliyuncs.com/docker-ce/...` 返回 `SSL: no alternative certificate subject name matches target host name`。不接受关闭校验，因此仓库 `baseurl`/`gpgkey` 保留 `https://mirrors.aliyun.com`，未按 M13 指南改为内网 HTTP。
4. **`dnf-plugin-releasever-adapter` 已预装**（`1.0-3.al8`），M13 指南中的安装步骤被跳过，未重装；其 `[releasevermapping] 3 = 8` 使 Docker 仓库解析到 CentOS 8 路径，符合预期。
5. **镜像内容停留在 2024-05**：`docker-ce-stable` 的 `Repo-updated` 为 2024-05-23，可安装最高版本是 `docker-ce 26.1.3`（Compose 2.27.0、buildx 0.14.0）。若后续需要更新版本，需先解决官方源可达性或换用更新的镜像源，属独立决策。
6. **SSH 无 PQ KEX**：每次连接都打印 post-quantum 警告；不影响本次身份校验，但说明服务器侧 `sshd`/OpenSSH 较旧。未修改 `sshd`。
7. **容量未验证**：1.8 GiB / 无 swap 下运行 M13 九服务栈的可行性仍属未知；Docker 本体启动后可用内存约 1.5 GiB，这不构成该栈可用的证据。

## 13. 复现命令附录

完整可重放序列（不含任何私钥或口令内容；`<KEY>` 指会话附件中的私钥路径，只作 `-i` 参数）：

```sh
# 0. 连接（严格主机身份）
ssh -i <KEY> \
  -o UserKnownHostsFile=P:/CRM/.tower/worktrees/wt-10/deploy/.runtime/m10-known_hosts \
  -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o BatchMode=yes dev@8.133.190.46

# 1. 只读预检
ssh-keygen -lf <m10-known_hosts>          # SHA256:JHFV75F2oc1tYqjd4viv130aknkd7fOwtKEpmGtgy80
sudo -n true                              # 免交互提权可用
nproc; free -m; df -h /; swapon --show
rpm -qa | grep -Ei 'docker|containerd|podman|runc'
systemctl list-unit-files | grep -i docker

# 2. key 获取与核验（关键指纹 pin）
umask 077; cd "$HOME/c010500-docker-install"
curl --fail --location --proto '=https' --tlsv1.2 -sS -o docker-release.aliyun.gpg \
  https://mirrors.aliyun.com/docker-ce/linux/centos/gpg
curl --fail --location --proto '=https' --tlsv1.2 -sS -o docker-release.tuna.gpg \
  https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/centos/gpg
sha256sum docker-release.*.gpg && cmp -s docker-release.aliyun.gpg docker-release.tuna.gpg
gpg --show-keys --fingerprint --with-subkey-fingerprint docker-release.aliyun.gpg
# 期望：060A 61C5 1B55 8A7F 742B 77AA C52F EB6B 621E 9F35
sudo rpm --import docker-release.aliyun.gpg && rpm -q gpg-pubkey

# 3. 仓库配置（同一 HTTPS 源，不覆盖既有文件）
curl --fail --location --proto '=https' --tlsv1.2 -sS -o /tmp/docker-ce.repo.upstream \
  https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
test ! -e /etc/yum.repos.d/docker-ce.repo
sudo install -m 0644 -o root -g root /tmp/docker-ce.repo.upstream /etc/yum.repos.d/docker-ce.repo
dnf repoinfo docker-ce-stable     # baseurl 应解析为 .../centos/8/x86_64/stable

# 4. 事务审查，再确认（不使用 -y / 不使用 yes 流水线）
sudo dnf --setopt=assumeyes=False --assumeno install \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
printf 'y\n' | sudo dnf --setopt=assumeyes=False install \
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. 启动与验证（不 enable、不拉镜像、不建容器）
sudo systemctl start docker
systemctl is-active docker; systemctl is-enabled docker
sudo docker --version; sudo docker compose version; sudo docker buildx version
sudo docker info | grep -E 'Server Version|Storage Driver|Containers|Images'
docker info            # 无 sudo，应 permission denied
id dev                 # 不应出现 docker 组
```

审计暂存目录 `/home/dev/c010500-docker-install/` 保留两份 key 副本（仅公钥、`0600`）作为来源证据；若需清理，由管理员另行决定，本轮未删除。

