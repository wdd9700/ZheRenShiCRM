# S023 原生日程发布卡 — **HOLD，不切换**

本卡复用 [§24.3–24.6](../../docs/REMOTE_EXECUTION_C010600.md#243-经批准的定点操作入口) 的定点服务思路，不复用其中的 S011 目标或确认命令。S023 未连接生产或本地试用站、未构建/加载镜像。**当前实际动作只有审计与保持 M48 原样：不上传、不安装 include、不替换 backend。**

## 冻结件与审核

| 角色 | 本机冻结制品 | config SHA256 |
|---|---|---|
| M48 的原 frontend / 基础栈 e14b6 | `P:/CRM/.tower/worktrees/wt-37/deploy/.runtime/final-navigation-release-e14b6cce43cf/image.tar` | `c2601699d018675f1e2fc87a13c7fa4963090182eccfc70a8e51ed5ccdfbe062` |
| M51 构建 S021 | `P:/CRM/.tower/worktrees/wt-51/deploy/.runtime/native-schedule-cd2df0cf985145d6be871af1f2ec6b27-candidate/image.tar` | `7ec179f1c0635f735aa6d59e6075f695f61e5a72739a1ea866c4e604e5bcf58a` |
| 实际 M48 还原目标 | §24.4 原三份 Compose（含持久覆层）、M48 原归档/已加载镜像 | `42f21f6359bd61aa4dd2a84b4ce50df96197a30688b1e0b298e5f8309d80318e` |

没有用 `c260` 冒充 M48 **后端**：M48 的第 17 层只增加旧入口 HTML，未改原 frontend 静态资产。本机实物对比用 e14b6，不等于运行中卷/文件已现场核验。工具先固定两份归档整体 SHA、OCI index/平台 manifest/config 和 16 个继承层，再用真实层字节和 whiteout 比较 `/assets` 的普通文件（按 `sites/assets` 的四个已知 app 别名）；检查 candidate 后两层不会改到公开 `node_modules` 链接目标，不把源码映射当发布文件。[static-delta.tsv](static-delta.tsv) 是变动 URL／长度／SHA256 清单（`-` 表示该代镜像中没有）：**103** 个 `coexist-exact` 是出现在镜像内 M51 可达依赖证据中的新增指纹 JS/CSS，**197** 个 `retain-old` URL 仍由原 frontend 服务，**101** 个 `exclude-sourcemap` 不上宿主，**3** 个 `block-same-url` 禁切。实际资产不随 Git 提交。

用本机 Python 3.9+（不是生产的系统 Python）。从仓库根目录，令 `OLD` 和 `NEW` 为上表两份本地 tar：

```bash
set -o pipefail
python -B deploy/native-cutover/static_plan.py "$OLD" "$NEW" | diff --strip-trailing-cr - deploy/native-cutover/static-delta.tsv
python -B deploy/native-cutover/static_plan.py "$OLD" "$NEW" --format nginx-review  # 逐 URL，只有注释
python -B deploy/native-cutover/static_plan.py "$OLD" "$NEW" --format gate          # 预期拒绝：3、stdout 为空
```

`ledger`/`nginx-review` 的 0 只表示审核输出生成成功，**不是放行**。当前工具固定这对 tar，没有强切参数，也不生成未注释配置或可上传文件。M51 回环 `s021qa-cd2df0cf/runtime-proof.json` 的新入口 `index-DuOUFOxf.js`、懒加载 `TeamSchedule-CW3BMQ5I.js`、`TeamSchedule-CJdLjCd3.css` 三个 SHA 与清单相同；既有回环普通身份及兼容关闭证据不等于生产验收。

### 为什么不能只发布哈希 JS/CSS

- 原内层 Nginx `/assets` 为 `try_files $uri =404`，不是后端 fallback；宿主 HTTPS 则将此路径代理给原 frontend。因此仅换 backend，会让新 CRM HTML 引用原 frontend 缺少的资源。若未来保持这套拓扑，必须有**新增资源的同源供给路径**。独立宿主 HTTPS 精确 location 是不改原 frontend/共享卷的可回退做法；不能用 `/assets/` 或 `/assets/crm/frontend/` 整段接管，也不能改现有 TLS、私有文件或升级包路由。
- 两代 `/assets/crm/frontend/index.html` 与 `/assets/crm/frontend/sw.js` URL 相同、内容不同（同名 `sw.js.map` 也不同，只是调试文件）。两代 CRM HTML 引用同一字节的 `registerSW.js`，显式注册 `sw.js`，scope 为 `/assets/crm/frontend/`，恰与 SW 文件目录的默认 scope 相同。该 worker 可以控制这一静态前缀下的**客户端文档**，但不因 `/crm/` 页面请求了此前缀下的 JS/CSS 就获得对该页面的控制；不能据此宣称 `/crm/` 用户已遇到离线、串包或登录故障。`sw.js` 的 `skipWaiting`/`clientsClaim`、各代 shell 的 revision 及不同的 precache 表仍是同一注册地址的两套承诺。只供新哈希会继续留下旧 worker/shell；覆盖固定 URL 则改变老客户端的更新内容且恢复服务配置不立即撤销浏览器安装的 worker/cache。因此不能以任一方案冒称完整制品并存；同样不能靠 query 绕过同一 scope，或临时扩大 `Service-Worker-Allowed`。
- 最短后续候选方向（不是本轮修改）：保留旧固定路径和缓存；只将新 PWA 的注册脚本/worker/shell及其专用依赖移到明确的新版本子目录，绑定新 scope 与独立缓存身份，`precache` 使用配对 shell 和同源明确的哈希 URL，不以 SW 接管认证 `/crm/`。若用 `frontend/` 下的更深路径，要保证最长 scope 匹配且不会误走旧 worker 的导航 fallback（可用非嵌套前缀避开旧 scope）。只做一项新的关键验证：同一真实浏览器 profile 预置旧 worker/cache 与普通会话，升级再回滚一次，观察新旧 worker 各自拿到配对资源、原会话与数据保持、`/crm/` 不受其控制；不清浏览器缓存、站点数据或要求客户重新安装。验证不通过就保留 HOLD。

## 条件操作卡（仅未来新制品独审、解除 HOLD 且获生产排他授权后）

1. **锁内核基线并封存。** 复用 §24 原 M48 锁 `/home/dev/c1118-schedule-return-d4330d3/backend-only.lock`，另确认没有不持锁的全栈 Compose、其他运维或证书并行重载；无法排他则停。核实际 M48 状态原字节、其持久 `backend-only/backend.yml`、原 Compose/HTTPS 基础配置、`CRM_IMAGE=sha256:c2601699…`、基础 release/layers 与原 R2 记录；无需更改它们。核实际 backend `42f21f…` + HTML `cdb9e49a…`、原 frontend `5aabd604…` 的完整身份和 Nginx master、DB/双 Redis/其余服务与卷健康、原生四件备份齐全可读；保存本窗口严格非目标快照与 M48 活动状态的精确字节。确认原 M48 镜像仍可用，并备好正常登录的普通 Sales User 可信 HTTPS 会话。任何漂移不得重采历史快照绕过。
2. **先配静态、再换一个服务。** 新审核包需将同一新 config 的不可变静态文件放进独立 root-owned 无链接目录，逐件校验长度/SHA；对照现场 `nginx -T` 和旧 HTTPS 资源查 MIME、Cache-Control、Content-Encoding、CSP/其它安全头、`nosniff` 与 GET/HEAD，不能因另写 `add_header` 丢继承，不能改变旧 URL。选择 TLS server 内单独纳入的 exact locations，原子安装/撤回单一配置入口，`nginx -t` 后仅优雅 reload；回读新/旧代表性 URL 的同源无重定向 bytes/SHA、头和方法限制，失败即全撤静态，不能进入 backend 切换。另核新包归档链/有序 diff_ids、预加载并按 config 核镜像。不使用 R2 的 `switch`，它针对 c260 → 42f21f。
3. **目标化变更并验收。** 在原三份 Compose 上以第四份受审覆层只覆盖 `services.backend.image`；按 §24 对两份 `config --format json` 还原唯一不同字段后比较全对象（不输出 env）。私有持久目录保存覆层、快照及状态，切前原子记录本轮 switching、切后 awaiting-https，不写全栈 ready。维持原 project/env/Compose 参数及顺序，只对加了第四覆层的同一 Compose 调用 `up -d --no-deps --pull never --no-build --force-recreate backend`；禁全栈 up/update/stop/restore。按 §24.2 检新 config、模板、backend health、bridge IP 与原 frontend 内唯一 DNS、双方 pong；仅有需要且原身份未漂移时在原 frontend 内 `nginx -t` 后 `nginx -s reload`，不重建/重启容器。确认非目标快照与旧 `/socket.io` 路径保留。一次真实 HTTPS 普通会话：线索 → 团队日程（新入口、懒加载 JS/CSS 及直接刷新）→ 商机，确认同窗/同侧栏/同登录；旧 `/team-schedule` 仍返回 M48 风格兼容页（开关默认关闭，不改 `site_config.json`）。不写业务；成功才记本轮 active，未做实体 Electron 不声称通过。
4. **失败只回 M48。** 保持同一锁和窗口证据：若已换 backend，仅移除第四覆层，用原三份 Compose 对 backend 执行同一条命令，明确仍带 `/home/dev/c1118-schedule-return-d4330d3/backend-only/backend.yml`，必须渲染 `42f21f…`；若已经是正确 M48 config+模板，不重复重建。核 `cdb9e49a…`、健康/IP/DNS/双 pong、必要的原内层优雅 reload、非目标均未动；随后撤本轮宿主静态入口，`nginx -t` 与 reload，留文件及证据。真实可信 HTTPS 确认旧 CRM 入口 `index-DO6EgA-F.js` 和旧日程“返回 CRM”后，才原子恢复**本窗口封存的 M48 active 原字节**。若仅预发布了静态，仅撤入点、复核原服务，不动 backend。状态不明、快照漂移或恢复失败即保留明确故障和现场停止，不重采快照，不手写 ready；不用 R2 `rollback`/`accept-rollback`、`restore-old-lock`，不退至 c260 后端，不重建 frontend/Aegis、DB、双 Redis 或其他服务，不覆库、不迁移或刷新 Redis/浏览器数据。上线、回退自动或中断续作未在生产执行；新版本须复审本卡配对步骤，不把已安装 R2 当成具备 §24.5/24.6 本地新命令。
