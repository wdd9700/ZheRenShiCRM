# H010｜8.133.190.46 可信 IP HTTPS 入口

## 交付状态与边界

本变更是供 **M17 单一操作者**执行的配置与受控步骤，不是已上线报告。入口固定为 `https://8.133.190.46`；客户端直接连真实服务器，不用本地 SSH/HTTP 中转。宿主 Nginx 到同机 Docker 的 `127.0.0.1:8088` 是正常内部反代，不是客户端本地中转。

| 项目 | 本次状态 |
| --- | --- |
| M17 最新目标事实 | Nginx1.24已安装，系统Python3.6保持；80本机challenge200/监听0.0.0.0，公网连接超时；Docker仍仅发布 `127.0.0.1:8088`；官方离线Certbot image已standard load、config/11层/原始Config全等，但RepoDigests=[] |
| 云安全组、外网 80/443 可达 | **80公网仍未通，SG原因未确证，M17负责定位**；本任务不重复网络探测、不读云凭据、不自动关闭防火墙 |
| staging / production 实际签证 | **未执行**；不能把制品加载或官方能力当成功签证 |
| 本地受控回归 | 离线config-pinned修复后22项Python unittest通过（含缺image/错ID/错层拒绝、合法离线及在线统一寻址）；原安全回归保留；`bash -n deploy/remote/trial.sh`、`git diff --check`通过 |
| Linux Nginx 配置解析、Compose 实例启动 | **未执行**；本机无 Nginx、Docker daemon 不可用，未启动 WSL/另造环境；M17 必须先执行下述测试再 reload |
| 真实 HTTPS 原生登录、Secure cookie、CSRF、认证 socket | **未执行**，由 M17 最后一次直接公网入口烟测记录，不能用 ping/Engine.IO open 代替 |

不修改业务数据、账户口令、CSRF、TLS 校验、DB/Redis、Docker 网络或端口；不卸载应用、不删卷。内部真实 Frappe site 仍为 `crm.localhost`，不是用户要访问的 URL。不默认设置 `host_name` / `ssl_proxy`。

## 选择及证据

H010（2026-11-09，Provisional）：采用宿主 Nginx + HTTP-01 webroot + Certbot >=5.4 的 IP SAN `shortlived`。原因是无需域名、不停 Web 服务续期，且不公开 8088。备选 standalone 会争用 80 / 打断续期；Certbot nginx installer 尚不支持 IP；自签名不能满足可信 TLS，均不选。用户已授权服务器安装部署；无新增用户价值/授权卡点。主控将本 scope 内决策索引至总决策链。

官方依据：
- [Let's Encrypt / Certbot IP webroot（2026-03-11）](https://letsencrypt.org/2026/03/11/shorter-certs-certbot/)：webroot 必须 Certbot >=5.4，`--ip-address`、`shortlived`、deploy hook。
- [IP 与六天证书 GA](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability/)：IP 证书约 160 小时，必须自动续期。
- [Certbot 当前 CLI](https://eff-certbot.readthedocs.io/en/stable/man/certbot.html)：`--required-profile`、独立目录、renew、dry-run 和 hook。这里选 `--required-profile shortlived`，而不是仅 preferred 后允许回落。
- [固定上游 Nginx entrypoint](https://github.com/frappe/frappe_docker/blob/61d35da827ebc04d01b64c9e78385597ccebc9d8/resources/core/nginx/nginx-entrypoint.sh) 与 [template](https://github.com/frappe/frappe_docker/blob/61d35da827ebc04d01b64c9e78385597ccebc9d8/resources/core/nginx/nginx-template.conf)。M17 已确认现网的相关真实配置与其匹配；部署时再核当次镜像契约，不固定旧模板。

置信度：官方 CLI / 现网配置事实高；本机无运行时，签发、目标 scheme 与浏览器行为仍待实测。失败先保留现场，不以关闭 TLS/CSRF、忽略证书、改密码或扩大公网端口解决。

## 请求链与安全门

- 80：只接受 IP Host（可带 :80），只静态服务合法 ACME token 文件；其余 308 到固定 HTTPS IP；错误 Host 444。不反代登录/API。
- 443：IP 证书，TLS1.2/1.3；只接受精确 IP Host（可带 :443）；错误 Host 444。覆盖 Host、site、XFF、X-Real-IP、X-Forwarded-Host/Proto/Port；清空 `Forwarded`、`X-Forwarded-SSL`、`X-Forwarded-Protocol`，避免 Gunicorn scheme 头冲突。外层不用客户端提供的 XFF 链。
- `/socket.io`：保 Upgrade/Connection、cookie/Authorization 和超时；先拒绝非本入口 Origin（允许无 Origin 的受认证非浏览器客户端）。不改 CORS、不移除 socket 身份/namespace/room 验证。
- M17 真实内层存在 `map ... https https`，但 socket Origin 固定为 `https://crm.localhost`，外部 Host 为 IP 时认证会冲突。`prepare_inner.py --launch` 每次读取**当次镜像** `/templates/nginx/frappe.conf.template`，严格只改 socket Origin 为 `$proxy_x_forwarded_proto://$http_host`、backend XFF 为外层已清洗的 `$http_x_forwarded_for`；保 site header / protected files / 其余配置。每项必须仅匹配一次，漂移失败关闭。
- helper 保留镜像 main entrypoint（包括正常 assets 挂载准备），读取当次 `nginx-entrypoint.sh`，仅改临时模板输入路径，在正常 envsubst 后先 `nginx -t` 再 exec nginx。不会冻结上一镜像完整 conf，也不修改容器内原模板/原 entrypoint。下次更新若契约改变，frontend 启动失败，由既有维护流程保留现场，不能删守卫硬过。
- backend overlay 设置 Gunicorn `FORWARDED_ALLOW_IPS=*`，只在 backend **没有宿主发布端口**、Docker 网络只有可信项目容器、所有公网请求均经本入口及清洗头的前提下使用。8088 仍是 host-loopback；受信任主机用户与同网容器属于信任边界，不把这个 `*` 当公网安全设置。外层 `proxy_cookie_flags ~ secure` 是额外防护，不能替代验证后端真实 scheme / 登录 / CSRF。
- `trial.sh compose()` 自动识别固定 `/etc/crm-https/compose.yml`；拒绝 symlink、非 root owner、group/world 可写的 `/`、`/etc`、overlay 目录及两个文件。路径固定，不接受任意环境配置注入。无该目录时原命令不变。后续 `up`、`update-site-image` 等正常命令都会继承，不能只手动 Compose 一次后遗漏升级。
- 常用登录 POST（`/`、`/login`、`/api/method/login` 及 query `cmd=login`）每来源 IP 5 次/分钟、burst5，超额429，普通业务写入不套此速率。**这不是防暴力破解的完整保证**：Frappe 可从其他端点的 POST body 解析 cmd；分布式猜测/弱密码仍有风险。既有试用弱密码不在本任务擅改，M17 应记录既有 `allow_consecutive_login_attempts` / `allow_login_after_fail` 是否有效（只查这两个非秘密设置、不改）。优先在已有云安全组能力内将 443 限必要测试来源；不要无记录地声称弱密码已安全。

## M17 受控部署顺序

以下命令只在真实服务器运行。先使用审定 commit 导出的代码；`ROOT` 指现有 trial 根目录，`DELIVERY` 指本变更审定代码根目录，不能凭示例覆盖现有 `.runtime`。不打印 `.env`、cookie、口令、私钥、ACME account JSON 或含凭据日志。

### 1. 前检、快照、安装

1. 复用已知 80/443 / 8088 / 网络事实；同窗口核安全组与必要公开端口，不重新跑全套业务。保留当前镜像锁、Compose、trial.sh 和 Nginx 原配置的 root-only 快照；记录现有容器 ID/image/mount/ports，必要时用现有标准备份。此变更不做 migrate。
2. **真实目标为 Alibaba Cloud Linux 3 / dnf / RPM，系统 `/usr/bin/python3` 为3.6.8**，不是 Ubuntu。seq141 已纠正旧 apt/venv 方案：Certbot5.4官方 `Requires-Python >=3.10`，不能用系统3.6安装。M17 单次只读查询确认官方 `alinux3-updates` 有 `nginx` epoch1 `1.24.0-3.0.1.2.al8.1.x86_64`（满足本配置最低1.19.3），另有 Python3.11，但其 RPM 包含 `/usr/bin/python3` / unversioned-python，不能当安全旁路安装。本次**不装宿主Python、不改 alternatives、不替换系统解释器**。

主控已选现有Docker隔离Certbot，来源仍为官方 `certbot/certbot:v5.4.0`：linux/amd64 manifest `sha256:1dc5b4a99cce916f154c706569baf062600d7dea13e0711e7d7e1461d6230e39`、index `sha256:c23159d30afdd9c97960578aa4654f5901de6cae394958f894074dedd55e599d`，绑定config `sha256:f0cfa0056d76325c6a2d3f4dc4dc41449763a9ee1000ed11caf8dc180450144d`（Python3.12.10）。官方PyPI5.4.0 wheel SHA `2306d99ad7bf6f17858a95526a7f096a47fe9be0bd603b0434febf93ecf913a3` 已核Requires-Python>=3.10与console entrypoint `certbot.main:main`。

因目标与第一Ubuntu官方pull超时，Windows通过官方Registry→`production.cloudfront.docker.com`取得精确manifest全部12blobs，逐blob SHA/size和11个gzip解压diff_ids与原config全等，未换registry/重构image。生成标准Docker-load归档196956160B，SHA256 `feb4ef11bc19fee9e39c5579e85c0c481a6aec03f7d0819b68cdbf4ddd59dc19`；原manifest/config/blobs/verification保存在ignored `deploy/.runtime/certbot-official-image/`。M17已核双端tarSHA并standard load，实际config ID/11个有序RootFS diff_ids/原始Config相同；`RepoDigests=[]`且原manifest引用No such image，**不能伪称RepoDigest保留或制造digest tag**。

本版最小兼容统一按上述固定config ID运行：每次preflight及签证/续期构造容器命令前，用固定本机Docker socket `image inspect`该硬编码ID，要求恰好一个image、Id精确相等、linux/amd64、RootFS.Type=layers、11个有序diff_ids与代码固定清单逐值完全相等；缺镜像/错ID/错平台/缺层/错层/层顺序变动即拒绝，不pull、不fallback tag、不接受CLI/环境/用户自报image ID。config ID是原config JSON的内容哈希，原官方manifest→config/压缩blob→diff_ids来源链保持上述证据，不依赖load产生RepoDigest。在线按原manifest正常pull所得同一image也统一走此固定config检查；在线下载来源不改。digest身份不等于签名认证，也不把Registry读数/load成功当目标运行成功；M17须在本次定向独审后执行无网preflight实查Python/Certbot。无Dockerfile重建、无宿主pip/新venv。

Nginx只用已存在的官方 `alinux3-{os,updates,module,plus,powertools}` 源。M17实查这些源 `gpgcheck=True`、`sslverify=True`，`repo_gpgcheck=False`；既有key URL为 `http://mirrors.cloud.aliyuncs.com/alinux/3/RPM-GPG-KEY-ALINUX-3`，不改该URL、不声称仓库元数据有签名。先核既有 `gpg-pubkey-cac33616-5fb603a2`（既有记录见 `REMOTE_INSTALLATION_C010500.md` §7）；保留dnf包签名校验，不导入未知key/不启EPEL或额外module、不用 `--nogpgcheck` / `--allowerasing`。下列是目标执行路径；安装前查看事务只包含所需Nginx/OpenSSL/CA依赖，不应替换Python，出现意外替换即停，不放宽TLS指令。

```sh
/usr/bin/python3 --version
readlink -f /usr/bin/python3
rpm -qf /usr/bin/python3
rpm -q gpg-pubkey-cac33616-5fb603a2
sudo dnf --disablerepo='*' --enablerepo=alinux3-os,alinux3-updates,alinux3-module,alinux3-plus,alinux3-powertools \
  --setopt=gpgcheck=1 --setopt=sslverify=1 --assumeno install \
  'nginx-1:1.24.0-3.0.1.2.al8.1.x86_64' openssl ca-certificates
# 上条assumeno正常拒绝安装；核事务后才执行实际安装并保留签名验证结果。
sudo dnf --disablerepo='*' --enablerepo=alinux3-os,alinux3-updates,alinux3-module,alinux3-plus,alinux3-powertools \
  --setopt=gpgcheck=1 --setopt=sslverify=1 -y install \
  'nginx-1:1.24.0-3.0.1.2.al8.1.x86_64' openssl ca-certificates
# 在线正常来源路径保留；本次M17已完成离线load，不重复pull或安装。
# 新机器网络可用时：
# sudo /usr/bin/docker --host unix:///var/run/docker.sock pull --platform linux/amd64 \
#   certbot/certbot@sha256:1dc5b4a99cce916f154c706569baf062600d7dea13e0711e7d7e1461d6230e39
# 离线归档须先核上述tarSHA，再standard docker load；本次该步已由M17完成。
# sudo /usr/bin/docker --host unix:///var/run/docker.sock load -i /ABSOLUTE/certbot-5.4.0-linux-amd64.docker.tar
# 安装后与安装前比较以上Python版本/链接/所属RPM，必须保持不变。
/usr/bin/python3 --version
readlink -f /usr/bin/python3
rpm -qf /usr/bin/python3
sudo /usr/sbin/nginx -v
```

管理脚本兼容Python3.6，shebang和所有手动/systemd入口固定 `/usr/bin/python3`，不用交互PATH找解释器；它不导入Certbot。签证/续期只在精确digest的容器内运行受支持Python，完成后由宿主校验证书、测试并reload；**无容器deploy-hook执行host脚本**。容器不挂Docker socket/宿主根/nginx/管理代码，不privileged、不发布端口、不用host网络；root用户+cap-drop ALL/no-new-privileges/read-only rootfs，只有各环境config/work/log及webroot四个必要目录可写，临时文件用tmpfs。显式挂载镜像声明的两个数据目录，避免匿名持久卷；`--rm`只清理本次短命签证容器，不碰既有CRM资源。运行 `--pull=never`，镜像不存在就报错，禁止续期时默默换tag。

3. ALinux RPM布局不是 Debian sites-enabled：先读取实际 `/etc/nginx/nginx.conf` 和 `/etc/nginx/conf.d/`，若新装默认server与本配置80 default冲突，仅备份并移开/正常禁用该**默认**server，其他配置不改。若default在主nginx.conf而不是独立conf，由M17保留完整原文件后只移除默认server块，`nginx -t`后才启动/加载；不能假定移动Debian链接就生效。确认Nginx active；安装目录不能是symlink，root:root、不可group/world写。

```sh
sudo install -d -m 0755 /usr/local/lib/crm-https
sudo install -m 0755 "$DELIVERY/deploy/https/manage.py" /usr/local/lib/crm-https/manage.py
sudo install -m 0644 "$DELIVERY/deploy/https/http.conf" "$DELIVERY/deploy/https/tls.conf" /usr/local/lib/crm-https/
```

4. 用审定字节更新 `deploy/remote/trial.sh`，保留旧脚本，核公开 SHA。该文件变化已单独获 scope 批准；`SOURCE_SHA256SUMS` 实际只覆盖53件 app/build 文件、不含 trial.sh，**本变更不刷新它、不冒称脚本仍是原242161工具字节**。旧的 `apply-tools-update.sh` 只接受指定旧来源，不可拿它强装新版本；M17 按审定单文件 SHA 定点安装并对账，现有 image/release/运行材料不改。

### 2. 只启用 HTTP 验证入口，staging 再 production

```sh
sudo /usr/bin/python3 /usr/local/lib/crm-https/manage.py preflight
sudo /usr/bin/python3 /usr/local/lib/crm-https/manage.py bootstrap
```

`preflight` 无签证/配置写入：核固定宿主解释器>=3.6、Nginx>=1.19.3，再先核固定config ID/平台/11个有序RootFS，按此config ID、network none、仅tmpfs运行 `/usr/local/bin/python`，断言容器Python>=3.10并执行官方 `certbot.main:main(['--version'])`，要求Certbot>=5.4。缺镜像/错误版本直接失败，不自动pull/改软件源。`bootstrap` 原子写受管理 conf，先 `nginx -t`，失败恢复原文件且**不 reload**；已有非本工具管理的同名 conf 拒绝覆盖。成功才 reload。不要在生产激活后再运行 bootstrap（它会回到仅 HTTP 验证配置）。`/var/lib/crm-acme` 为 root:root 0711 仅可穿越，webroot0755；staging/production 工作目录0700。ACME account/私钥目录在 `/etc/crm-acme/{staging,production}`0700，日志另放 `/var/log/crm-acme/...`0700，不在仓库。

M17 在 webroot 的 `/.well-known/acme-challenge/` 建一个无秘密随机 token，**从外网直接** `http://8.133.190.46/.well-known/acme-challenge/TOKEN` 读回；仅自己删除该探针。检查错误 Host 不提供 challenge/业务、`/login` 只308。若80不可达，保现场报告安全组/网络问题，不关闭防火墙或改80承载登录。

```sh
# 主控已明确选无邮箱登记；不借用试用账号邮箱、不编造维护邮箱。
sudo /usr/bin/python3 /usr/local/lib/crm-https/manage.py issue-staging --register-unsafely-without-email
sudo /usr/bin/python3 /usr/local/lib/crm-https/manage.py issue-production --register-unsafely-without-email
```

`--register-unsafely-without-email` 是官方显式选项，staging/production同样原样传递；与 `--email` 互斥，未选任一模式即拒绝，不静默无邮箱。日后只有已有获准维护邮箱时才可显式改用 `--email`。**无邮箱就没有账号邮箱联系/提醒渠道**，不能依赖CA发邮件发现失败；继续依赖现有timer、journal和48h检查，不另建告警平台。

两环境宿主config/account/work/log及显式CA完全隔离，分别映射到容器相同的 `/etc/letsencrypt`、`/var/lib/letsencrypt`、`/var/log/letsencrypt`，webroot映射到 `/var/www/certbot`，相对live→archive链接在宿主仍有效。只由宿主post-success处理production；staging不reload/不进入443。无 `--force-renewal`，重复调用保留尚未到期证书；短证书profile不存在即失败、不回落。宿主脚本/systemd使用umask0077；官方webroot自身按022/0644创建公开挑战文件，私钥root owner且不得group/world读、不输出/不提交。首次production成功只验证证书，不提前打开HTTPS；容器内不设置host deploy-hook。

### 3. 持久内层覆盖，测试后才启用443

只在已安装新 `trial.sh` 且其来源审定后操作；先备份原状态，再完整安装两个文件。目录存在期间缺文件会被安全拒绝，勿并发运行升级。

```sh
sudo install -d -m 0755 /etc/crm-https
sudo install -m 0644 "$DELIVERY/deploy/https/compose.yml" /etc/crm-https/compose.yml
sudo install -m 0644 "$DELIVERY/deploy/https/prepare_inner.py" /etc/crm-https/prepare_inner.py
```

M17 使用现有项目同一 `.env` / image.env 及以下参数（不输出 `config` 正文）先验证合并，再**仅重建 backend/frontend**；不重建 DB/Redis、不换镜像，不改挂载/端口/业务。`config --quiet` 不能代替实际 `nginx -t`，后者由动态 frontend wrapper 启动前执行。

```sh
sudo -n docker compose -p crm-trial-c010400 \
  --env-file "$ROOT/deploy/remote/.runtime/.env" \
  --env-file "$ROOT/deploy/remote/.runtime/image.env" \
  -f "$ROOT/deploy/remote/compose.yml" -f /etc/crm-https/compose.yml config --quiet
sudo -n docker compose -p crm-trial-c010400 \
  --env-file "$ROOT/deploy/remote/.runtime/.env" \
  --env-file "$ROOT/deploy/remote/.runtime/image.env" \
  -f "$ROOT/deploy/remote/compose.yml" -f /etc/crm-https/compose.yml \
  up -d --no-deps backend frontend
sudo /usr/bin/python3 /usr/local/lib/crm-https/manage.py activate
```

内层未健康/语法失败就停止，不 activate。`activate` 先验证 production IP SAN、系统信任链、私钥权限/公钥匹配、证书有效期<=160h、剩余至少24h，再原子安装 HTTP+TLS conf、`nginx -t` 后 reload。reload后用系统信任校验连本机443（校验目标 IP），比对实际服务 leaf DER 与当前 production leaf；只短暂等待 reload 生效。失败恢复旧 conf；若未尝试 reload，不 reload；已尝试才测试并回载旧配置。此本机探针不是外网/浏览器验收。

### 4. 自动续期及可见失败

```sh
sudo install -m 0644 "$DELIVERY/deploy/https/crm-ip-renew.service" "$DELIVERY/deploy/https/crm-ip-renew.timer" /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/crm-ip-renew.service /etc/systemd/system/crm-ip-renew.timer
sudo systemctl daemon-reload
sudo systemctl enable --now crm-ip-renew.timer
sudo systemctl start crm-ip-renew.service
sudo /usr/bin/python3 /usr/local/lib/crm-https/manage.py check
sudo systemctl list-timers crm-ip-renew.timer
```

每小时17分+最多5分钟抖动，Persistent补跑；unit显式依赖既有Docker服务。容器里的Certbot自行判断临期，不小时强签；容器失败直接非零，宿主不reload。容器成功后宿主校验production链/IP/权限/公钥/寿命及**剩余48小时**，再核实际服务leaf；若已等于磁盘证书就不重复reload，若不一致或TLS探针失败则先重新校验证书、`nginx -t`、reload、再核实际leaf。没有让容器hook调用宿主脚本，因此不会出现“Certbot吞hook错误仍报成功”；宿主post-success任一检查/reload失败直接导致unit failed、journal可见，拒绝“磁盘已续/服务仍旧”。`check`也核timer active/enabled，不因一次成功就承诺未来永不失败。

运维最小可见检查（已有监控若可接入，只读此退出码/failed unit，不传私有日志）：

```sh
sudo /usr/bin/python3 /usr/local/lib/crm-https/manage.py check
sudo systemctl status crm-ip-renew.service crm-ip-renew.timer --no-pager
sudo journalctl -u crm-ip-renew.service --since '1 day ago' --no-pager
```

本任务不另建监控平台、外发告警/邮件；因此**无人查看journal/failed unit时不会主动通知人，无邮箱模式也没有CA邮箱联系/提醒渠道**。运营方须把非零/failed接入既有监控或承担每日检查。失败不得通过强制连续签发凑绿（有CA rate limit），不设置容器host deploy-hook、不用 `--break-my-certs`。

## 一次直接公网验收（M17填写结果，不穷举）

1. 系统正常信任验证访问 `https://8.133.190.46/login`，IP SAN/链可信、无 `-k`；80 `/login` 308，错误 Host 拒绝；8088仍仅loopback，DB/Redis无新增发布。
2. 原生表单以既有获准账号登录→CRM。记录 `sid` **属性而非值**：Secure、HttpOnly、SameSite=Lax，Domain 不含内部站点；所有跳转/业务 URL 为公网 HTTPS IP，无 http/internal Location。读取受认证身份只记是否正确，不记cookie。用既有正常写操作证明合法CSRF可用，再一次错误CSRF请求应拒且无副作用；不关CSRF/不注入sid冒充登录。
3. 同一浏览器会话验证 `/socket.io`：Engine.IO polling/open或101只是传输；还须实际 namespace `crm.localhost` 完成 cookie认证并收到正常连接确认/既有业务通知（内部 namespace 不等同可访问URL）。错误公网 Origin 在外层403；不用匿名open代替认证。认证/room权限逻辑不在本任务修改。
4. 记录 production签发时间/公开序列或指纹/到期时间、timer next/last与service结果、云安全组实际状态、上述各项PASS/FAIL。证据写 M17 运维记录；**本文件首表当前仍是未实测状态**，不得提前改成PASS。最后保留一次正常镜像升级将自动继承overlay的事实及当次模板测试，不重跑所有原业务suite。

`host_name` 目前不设置：真实现网缺该配置，当前请求以公网Host+https scheme路由。如果实际证据出现后台生成绝对URL泄漏内部地址，只由M17先记录该单项原值/是否存在，再用正常 `bench --site crm.localhost set-config host_name https://8.133.190.46`，清本站相关缓存并定点复验；回退恢复旧值，原先不存在则 `bench ... set-config --remove host_name`（先核当版CLI）。不覆盖完整site_config、不改DB口令、不用ssl_proxy猜测掩盖错误scheme。

## 回退

- 签发或检查失败且未 activate：保仅80 challenge/308，保全部账号/证书与Docker原状态，报告原因。不回退到80登录，不暴露8088。
- 线上登录/socket/CSRF不满足：先撤下本任务443配置或在云SG限制443，恢复本轮**已保留**原Nginx conf，`nginx -t`成功才reload；如果原先没有公网入口，就恢复无公网业务入口，而不是降级HTTP。停止timer避免对已撤配置重复reload，保ACME数据以便修复。
- 要撤内层overlay时先关闭公网443，再将 `/etc/crm-https` 整目录移动到 root-only 备份位置（保留，不删除）；按原Compose和原镜像只重建 backend/frontend。确认ID/image/volumes/ports与预期，不migrate、不删卷。没有overlay的新trial.sh自动回原命令；需要回旧trial脚本时按快照/SHA恢复。不要仅删某个overlay文件留下半配置。
- 不自动卸载nginx/Certbot、不撤防火墙、不删除证书/账号/业务。不因“回退”把已保护私文交给不含安全扩展的旧镜像。

## 本地回归命令

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s deploy/https -p 'test_*.py' -v
bash -n deploy/remote/trial.sh
git diff --check
```

这些只证明离线契约/受控失败路径与shell语法，不证明Linux nginx解析、真实ACME或生产登录/socket。线上执行与最终状态由M17负责，M43不另开远端窗口。

## Socket 认证回调的已知待验边界

固定 [Frappe realtime/utils.js](https://github.com/frappe/frappe/blob/v15.125.0/realtime/utils.js) 在 common 配置没有同时设置 `webserver_host` 与 `webserver_port` 时，以 socket Origin 作为认证回调基址。因此修正 Origin 后，websocket 容器会正常校验证书并回调 `https://8.133.190.46/api/method/frappe.realtime.get_user_info`，保内部 site header 和 sid/Authorization。**M17 需在同一次实际认证 socket 烟测确认公网 hairpin 可达**；本变更没有预先改全局配置。

若且仅若证据确认该回调因公网回环不可达失败，可由 M17 记录 common 这两项的原值/存在性，通过正常 `bench set-config -g webserver_host http://backend` 与 `bench set-config -gp webserver_port 8000` 配置受信任 Docker 后端直连，重启单个 websocket 后定点复验。该内部 HTTP 回调不向浏览器下发 URL，不取消认证/TLS/CSRF，不写账户秘密，不把公共 Origin 改回内部站点。只先核这两个公开字段，不打印完整 common/site config；回退恢复原两项或按当版正常 CLI 删除原不存在的键并重启 websocket。其他业务/队列配置不改。

## 可选 Windows 签名更新静态目录（未发布、未启用 OTA）

为 M41 预留同一可信 origin 下 `https://8.133.190.46/updates/windows/`，不是另一个发布平台。当前无目录内容时返回404，不进入 CRM 登录/鉴权页，也不做3xx跳转。仅白名单：

- `manifest.json`：原 UTF-8 字节，<=16KiB。
- `manifest.sig`：原64字节 Ed25519 detached binary signature。
- `PhilosopherStoneCRM-Setup-<x.y.z>-x64.exe`：不可变的完整 per-user x64 安装器，<=512MiB。

Nginx 精确/锚定正则匹配上述名字，其他路径404，autoindex关闭，无上传/执行，只允许 GET/HEAD；manifest/sig `Cache-Control: no-store`，版本exe一年immutable；gzip关闭避免改变签名字节。不开放仓库、客户文件、Frappe public/private/files 或密钥目录。manifest/安装器大小与SHA/签名由已审 M41 本机发布工具及客户端校验，Nginx 不冒充签名器或格式校验器；不接受未签 latest.yml。

静态 root 为 `/var/lib/crm-public/current`，其下布局 `updates/windows/<allowlisted-name>`，**与 `/etc/crm-acme`、CRM卷完全分开**。由M17只上传本机已签的正式三个产物：先exe并核hash/size（同名已存在且不同则拒绝覆盖），再在 root-owned 新release目录准备原manifest/sig，核字节数、SHA/签名合同后，用同一文件系统原子替换 root-owned `current` 符号链接指向完整release快照；旧快照保留。release和父目录root:root不可group/world写、静态文件只读、不得放任意文件symlink/客户资料。新快照需含仍在使用的既有不可变exe，不能让旧manifest指向404。manifest/sig两次请求可能跨快照切换，客户端必须按既有签名失败关闭/重试合同处理，不能跳过签名。

**私钥仅留本机，不上传服务器**；公钥已固定于可信客户端，不从此站下载作为初始信任。HTTPS未可信、签名产物未实际发布前，客户端保持 OTA disabled；此配置不生成虚假manifest或exe。上线后M17用 `Accept-Encoding: identity` 直接公网读回，确认200/准确Content-Length/原字节hash，目录、其他文件、POST为404或403；不接受重定向。最后真实feed origin证据交主控决定何时启用，不在本变更擅自打开客户端开关。
