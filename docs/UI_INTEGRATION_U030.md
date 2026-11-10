# 哲人石CRM U030 标准组合与登录品牌

状态：最终2f92候选已完成标准构建、受影响产物定向检查、限定核心Terra视觉/正常退出及原归档验证，材料齐备请求最终独审。登录截图两次PAGE_NOT_READY未取得、可读白黑入口风格偏差及未全面多语言矩阵如实保留，不宣全视觉完美。M37没有更改线上服务、数据库或部署锁；未SSH/上线。最新身份、receipt、截图继承边界与交付包见文末，全部历史失败保留。

## 固定来源与集成决定

沿用 D010：不重装依赖、不从 master 旧 12 项补丁重建，不继续在 140 层旧镜像上累加。

- 固定 CRM：`36bd8859f2a6345a620477bc708d0546e8c3f08a`；Framework `15.125.0`。
- 现有两层基底：`crm-local:m9-lowdepth-ld2-195e623cfeb7458587597600e8e1e3e7`，index `sha256:e17300da434bd0c251adf618c86db26c718511fec6ab6bfe2a99e7fd91bebe41`、config `sha256:caf102a5716f4be0fc16ac9590038867bbe34c8e5419ff9fa92753ed6f1bf6d9`。原归档位置与完整证据见 `RECOVERY_VALIDATION.md` 首节；旧资源保留。
- M24：`9403d5a7ee4eb2d50eee3faf844d679a6aee5c80`，实核其 `frontend-patches/c011000` 相对已上线 `1c586261` 零 diff，包含完整 43 项。manifest SHA `2060a0f99a778797e8c2b2f97527ccc6bbf96288b7a23362d9319096fde177a3`。
- M30：`76f23be38dd993f32724c34d5184d8cf75c77146`，实核相对已上线 `4ff499e` 仅 README 变更。manifest SHA `74787afa31373457e9b91fa8ea6f53e4e3317854670656558579df0762b75670`。
- 顺序：M24 → M30 的已应用状态 → dark-ui → localization → branding → wording。导航对 AppSidebar 的重叠要求 M24 after 等于 M30 的 `c011000-resume` before；最终目标哈希按最后一个有序修改确定，不以“所有补丁独立”为假设。未知 before/after、遗失文件、payload 漂移及新增越界文件都拒绝。
- 已审输入：M35 `9f284b0d310b5ebd8f3570b66f216a23c793ef25`、M36 `c274caca0cf556754ed317a8c900a73a30f513ef`、M38 `50e0dd20613b58d4a6b5a46ef5e07a4f6e635a45`。父目录修复 `c0c8f92b24737b5146c1947b067ba68238001dc0` 已获窄审 clean/hold；hold 是最终组合/界面门，不再是目录代码阻断。

`prepare_ui_integration.py` 为独立的 U030 标准入口，不扩大旧 `prepare_integration.py`、`Dockerfile.frontend` 或 `verify_frontend_patch.py` 的白名单。v2 从四个完整 Git commit 导出有限补丁文件、原七件 UI 静态/模板覆盖，以及 `wording-overlays/` 下五件独立措辞输入；最终有效覆盖为八件（四件有序重叠，新增 `team_access/public/page.js`）。不复制整个 app，M38 分支没有的 M35 主题文件不会因此丢失，M36 词典保持。`ui_wording_manifest.json` 固定五组 before/after，准备时核 M35/M38 两端真实 Git blob，应用时再核实际前驱字节，最终 guard 使用 wording after 检查源码及根/sites 两份 page.js。准备 receipt 固定每个文件 SHA，Windows 准备后可从第一 Ubuntu 的同路径按 receipt 构建。构建仅产生候选，不激活站点；v1 历史 context 须用其原提交读取，不能混入 v2。

## 复现命令

不能使用移动分支或未提交工作树。此命令只准备来源：

```sh
python -B deploy/prepare_ui_integration.py \
  --dark-commit 9f284b0d310b5ebd8f3570b66f216a23c793ef25 \
  --localization-commit c274caca0cf556754ed317a8c900a73a30f513ef \
  --wording-commit 50e0dd20613b58d4a6b5a46ef5e07a4f6e635a45 \
  --integration-commit <U030完整40位审定提交>
```

保存输出的绝对 context 路径和 `ui-source-manifest.json` SHA。在明确的第一 Ubuntu 构建窗口内：

```sh
python3 -B deploy/prepare_ui_integration.py \
  --context <本checkout的deploy/.runtime/ui-随机标识绝对路径> \
  --context-sha256 <准备receipt的64位SHA> --build
```

`Dockerfile.ui` 先执行基底原 `verify_final.py after`，再快照完整五 app 源码与原资产守卫；仅运行新的三个 patch，已有 M24/M30 不重放。所有新 UI 目标核 after，原后端与非覆盖来源保持不变。资产阶段原映射 preseed → 原生 `bench build --app crm/team_access/team_schedule` → 根和 sites 双 manifest/全部映射目标/旧静态与新 theme、词典、login CSS/CRM HTML 引用实物强断言。依赖和 lockfile 不变，网络关闭；没有 pip/yarn install、migrate、install-app 或业务写入。最终镜像要求低于 16 层，不修改 daemon 或旧镜像。

## 登录、标题、语言与法律归属

branding 固定来源是从既有 caf102 归档选择性读取的公开源码，不读取 sites 或凭据：`frontend/index.html` SHA `6bb6dd5f737d7070264ed49e0fff78a049cc61c73b0c171d63419e0b866cd190`；`crm/hooks.py` SHA `0bb0b7f5974dce7e01844337902e4a5b66f5609cd8bc57b62f558c0846f70d55`。原始文件以 fixtures 保存并继续保留上游版权、publisher 和许可证。没有改 Python 包名、app_name、认证方法或任何权限 hook。

- 固定 HTML 的 title、Apple 安装名称为“哲人石CRM”；lang 来自 M36 透传的本次实际 `boot.philosopher_language`，并 HTML escape，不固定压成中文；没有实际值时才 fallback `zh`。
- `frontend/vite.config.js` 为第五个精确品牌目标，仅把 PWA manifest 的 name/short_name 两处变为“哲人石CRM”；registerType、workbox、start_url、icons、依赖、alias 均保持原字节，避免只改 Apple 名称而遗留 Windows/PWA 安装名。
- Framework 原生 `update_website_context` 在 login 控制器执行后处理展示 context；只作用 `path == 'login'`。保留原登录/重置密码/LDAP/OAuth/CSRF 结构，不替换 Framework 登录模板或登录 JS。
- 登录 title/app_name 用原生 `_`，共享 canonical theme 及局部 login CSS 通过 context head_html 加载；CSS 仅定位真实 `.page-card`、`.form-control` 等展示节点。没有 DOM 扫描、文本替换或认证行为改写。
- Framework base.html 的 Built on Frappe 注释及所有法律归属不变。品牌展示不代表重新授权第三方代码。

### 默认中文显式配置（当前未执行）

后续已授权集成/部署窗口，通过原生 System Settings 表单，仅把默认 Language 设置为 Chinese (`zh`)，记录原值便于回退。该项是用户要求的可逆显示设置，不是业务数据迁移；禁止批量改 User.language、时区、cookie、Accept-Language 或会话。

固定 Framework `translate.py` 的原生优先级仍生效：请求 `_lang`，Guest 的 `preferred_language` cookie 和浏览器 Accept-Language，登录用户语言/会话默认，最后 System Settings 默认。因此默认中文不强压明确英语或其他语言偏好；Guest 浏览器明确英语时仍可能显示原生英文，这是偏好遵从，不用 before_request 绕过。中文默认/英语用户/Guest 语言选择须在最终烟测中分别记录。

## 核验与剩余门

已运行 `python -B frontend-patches/branding/check_apply.py`：4 tests PASS，覆盖固定 fixture check/apply/after、重复应用拒绝、漂移/缺目标/未知 HEAD/既有新增目标拒绝、法律字段保留及仅 login context 展示和语言不覆盖。此处使用受控 HEAD，不冒称真实 Linux 构建或浏览器成功。

最终组合来源、receipt、Linux 构建、必要既有原生回归、最终镜像身份和 Terra 烟测结果将在实际执行后追加；未完成前不宣可上线。当前无必须交用户拍板的新增价值/授权卡点，普通技术选择可逆；线上更新仍是独立授权门。

### 接入预审 P1 修复记录

Sol 对 `d478ffbe004ea7fd7412f7949a228b532704aa09` 的预审指出：精确 caf102 基底没有 `crm/public/css`，原 branding 预检会在 `parent.resolve(strict=True)` 失败；旧测试提前创建该目录，掩盖真实构建阻断。这是实际生产路径缺陷，旧离线绿不能证明原构建可用。

修复只允许 `crm/public/css/login-theme.css` 的固定父目录缺失，解析已存在的 `crm/public` 并保留逃逸、链接、reparse、硬链接及普通文件检查。`--check` 不创建目录；全部来源/哈希预检通过后，应用阶段才创建这一层固定目录并暂存文件。暂存失败清理本次创建的空目录，不删除已有目录或资源。没有添加广义 `mkdir -p`、强制补丁或放宽目标白名单。

同一 caf102 归档目录元数据重新选择性核对：`crm/public` 存在（uid 1000/gid 0/mode 0755），`crm/public/css` 不存在。组合测试不再人为 mkdir css，以真实缺父目录起点运行。品牌测试增至 6 项并通过，补充只读预检保持缺目录、应用后创建目录、非目录父级/未登记父级/逃逸拒绝、暂存失败保持原字节且移除新空目录。组合回归及窄审状态以随后记录为准，仍未执行实际构建。

### 第一 Ubuntu 标准组合构建与最终镜像回归

实际输入为上述已审 M35/M36/M38，加 U030 `515125fb0d5dd67ef52f0d517099a498c8ba8fd1`；最后接入提交是独立 wording 增量，没有改已审父目录修复。准备 context `deploy/.runtime/ui-b9fcdc2639fa4e1abce34b8b7ea2cd29/`，`ui-source-manifest.json` SHA `ca7b2c30c703403936b2e85c29fbdf245183b8a68f498529a2bc4532bed5a32d`，六项离线组合检查通过，含真实缺父目录起点、55 CRM 来源/守卫、五措辞应用与未知 before 全部零写拒绝。

2026-11-08 唯一 `bash-xikg2tuh` / Windows PID59016，客户端总 **110.282秒、exit0**；Linux runner `07:54:31Z→07:56:05Z`。新候选（未激活站点）：

- tag：`crm-local:ui-b9fcdc2639fa4e1abce34b8b7ea2cd29`
- index：`sha256:d573751842d468c6a0649b9025668a009b225cbabc72802c29052da56c2070d9`
- linux/amd64 manifest：`sha256:d8f95f559a6e89ebd326e16b7353c81180034df313be2720432b68dd6d65bea2`
- config：`sha256:bf3ac000f58bae8d6e48128c1745de5f9d4d1e994238ba305a73b09770ae7de9`
- 实际 **7 层**；完整原运行 Config（User/Env/Entrypoint/Cmd/Volumes/WorkingDir 等）除新增明确 UI provenance labels 外与两层基底逐值相等。

原 `verify_final.py after`、M24/M30 43项、五 app 原来源/资产及新有序55项、canonical theme/词典、五 wording targets 均实过。原生 `bench build --app crm`（Vite **7.19秒**）及 team_access/team_schedule 标准构建均实际成功；双32键映射与全部实物、原保护资产、page.js、login CSS、PWA 安装名与 HTML 引用强断言通过。原 verifier 的 `da2177/b2b0e3a/two-target` 是历史输出文案，不是本次回退；实际43条精确 manifest 与新 labels/receipt另核。

同一最终候选新建 `network=none`、`restart=no` 的隔离 probe `a656e0beb92e38cfc62b4c989edbf9df216922f24bed863d86bf65f2e4663ec7`，实际运行：

| 命令/场景 | 结果 |
|---|---|
| `yarn test:run --reporter=verbose` | 34 files / 326 tests PASS，11.84秒 |
| 原 c011000 四 suite Vitest bridge | 1 file / 1 test PASS，1.39秒；原 child fail0/skipped0 强断言通过 |
| 原完整 App/Leads/FieldLayout 草稿→hidden→visible→恢复按钮 SFC | 1 file / 1 test PASS，10.49秒 |
| 测试前后完整来源/静态 guard | 全部 PASS |

没有 Unhandled Error/Rejection 段；保留日志中35处 ECONNREFUSED、3处 AbortError、既有 Vue 属性/aria 提示，不写成控制台无错误。离线 build 的 yarn 网络提示、Redis assets_json 无法连接及 chunk-size 警告保留；通过本地双 manifest/物理资产断言而非伪装连接成功，不为消除警告增装依赖。

前后8个资源守卫：原 **152 容器/126 卷**、daemon 身份与主 image lock 全等；只新增本次退出0且非 OOM 的 probe 与其两自有匿名卷（保留）。没有启动业务站点、migrate/install-app、读写业务记录、SSH、远端或第二 Ubuntu 操作；没有后台遗留。此处证明标准产物/源码场景成功，不替代真实浏览器登录及核心功能烟测。

完整结果 `deploy/.runtime/u030-build-f45eee7a38e4459ea3ff4b4a7f04ee73/result.json` SHA `6e5f7b62b9d02c945acabb46eda0692cbdba61b03a73a8bcd844994eb801a761`；同目录 `standard-build.log` SHA `f6b00f0db176d34760536623c5c88d714214c2e1fb3d94c92e952562702cc7d9`，`native-bridge-sfc.log` SHA `74622a9d313ba6ea29d0aad776b01620f38f20a865a83cc4c986e62a8f8a7689`。大报告/日志/镜像均 ignored，不进 Git。

### 最终产物日程/文案定向回归与静态 receipt

随后唯一 `bash-2npkjhcq` / Windows PID46512 **43.204秒、exit0**，没有重复前述326测试或重新构建。新只读根文件系统、none/restartno probe `853a265e9b3b28aa2ebce823537006fe5bfa11d7b3155cbefce4c2c02e41643f`，仅复用本次两个匿名卷为只读，写入只在 `/tmp` tmpfs。将**最终镜像的实际生产字节**复制 `/tmp` 并逐字节对照，用精确 M38 已有测试执行：

- Node 两 suite **34 tests PASS / fail0 / skipped0**，含任意分钟、短事件真实高度/标签、重叠列、跨日、DST 23/25小时、午夜滚动0、分页提示、会话清屏及迟到响应等场景。
- 既有四项 Python 静态合同 **4 tests PASS**；不重复第五个 Node wrapper，Node 已单独实际运行。
- M36 runtime 对真实 translation.js/词典/静态字典的占位符、context、locale、服务端优先级合同 **PASS**。
- 最终前后全部来源/资产 guard PASS；HTML 的 **78 个 CRM 静态引用**实物全在。

原153容器/128卷及 daemon/mainlock 四个守卫保持，只新增一个退出0、非OOM probe，无新卷。没有站点/业务/配置写入，无后台。第一 Ubuntu 独占已明确交 M9，由其按 tower 新授权复用既有 M32 站做真实 UI 准备；不能把准备计划当浏览器验收，M37不自行新站、安装、迁移或上线。

结果 `deploy/.runtime/u030-targeted-0b36337f5adf42cb80fc50293c3cb409/result.json` SHA `fb4fd9a2241e9ec091eeda6747ba3d716d8e32d81c6c1c242de439806057eed8`；`targeted.log` SHA `4c5982504b4d46f6008c0fe2a4b8c89a2ad42b904b5a683ff48e99225a2bb2bc`；`static-receipt.json` SHA `a5acfded3ccfe7292816d2644778d7383d2a06f9c07b19d729aa66972d5fd5cf`。

| 最终静态 URL | SHA256 |
|---|---|
| `/assets/crm/frontend/assets/index-DzM1uFIa.js` | `edbcc3204923cd0307e33afc64aef31ca252308d8cc4803e5fddd4cf5d782532` |
| `/assets/crm/frontend/assets/index-CyWp6XkC.css` | `3cf3fc9eb3d81c8c6ced733fff903cb465e535f155849ef16e72eefac7c4d816` |
| `/assets/crm/frontend/manifest.webmanifest` | `3637bb8e5f491d98fa1d3ee26441b615debc45a714f3572f29b00dac79f708b3` |
| `/assets/crm/css/login-theme.css` | `62a2c04cf3d98b2dceaf9bcffc1e39c0086cfd5cd2e46f9093fa4d29e2b93024` |
| `/assets/team_schedule/crm-theme.css` | `9b966e04566f7d83f0f18745ed5458d64fec2a77b12ae4c2a6042dbbf828b837` |
| `/assets/team_schedule/crm-zh-cn.js` | `adde7e9408c4aaefc960e78bfc1d49df9a2bc0061e474536ddb62e5ecca75f96` |
| `/assets/team_schedule/team-schedule.js` | `4c4e7996d66b1e200006f81dd52403ac20f96a300d8fbee00153de097c8eb8bf` |
| `/assets/team_schedule/team-schedule.css` | `a17e623c6b01b9a97b6d1f14f2ccdab0ca2bd6a71c0d1030980840466d40936b` |
| `/assets/team_access/page.js` | `188a4163fdeb7173b4c7a0f08cc9948c2c8ad9f7edc722fdab4535b3edb49931` |

### Terra 核心短测交接

后续使用**同一 d573 候选**，不另重建。M9计划在现有五 app M32 合成站只启动必要 infra 与新增 candidate backend/socket/frontend、铺精确已建资产，tower另授权唯一普通 Sales 合成账号与原生默认中文单字段。M37仅给上述镜像与静态 receipt，未读凭据。浏览器由 Terra 正常登录表单完成，不注入 cookie/DOM 或以 API 假装 UI：

1. `/login` 品牌/暗色/正常登录；默认中文与明确其他语言遵原生偏好；登录后 HTML lang/title 与侧栏品牌。
2. CRM 创建或编辑一条合成线索、添加备注/任务并看正常反馈；正常导航到团队日程并返回。
3. 日程纵向时间轴、任意分钟短事件/重叠/跨日可读，创建→编辑→取消的原核心功能；同源静态文件无404。
4. 私域活动/导入页只读检查中文与主题，确认字段 value、请求枚举与时区显示未变；不要重复完整后端权限/恢复矩阵。

上述是待执行清单，不是已通过。真实入口、账号保护文件路径及窗口收尾由 M9/tower交 Terra；遇失败保留首异常，按具体原因修复，不跳安全门。当前没有新增必须交用户拍板的价值取舍；正式线上部署仍不在本轮授权内。

## 集中视觉/引导修复第二批（v3，构建前）

首轮 d573 的 M32 UI 窗口已按固定期限收尾，M9明确释放环境：原语言 en、UTC、assets 与 infra 恢复；合成 SHORT active/OVERLAP cancelled 记录保留。首轮真实页面发现的品牌标记、低对比、引导硬编码与日程首屏布局问题由对应 owner 集中修复，不把首轮构建绿等同视觉验收。

本批输入：M35 `6e5c0473349b4f2f8914328af446660b1761427d`、M39 `23a36d60198adb8f2b16148ec197adf0bafc3181`、M38 新布局文案 `c558f997fecc7f1a4517b3716673bcdf76d63582`，三者均已主控确认 Sol clean/merge。不得继续使用旧 M38 `50e0dd2` 整文件覆盖新布局：其日程 HTML/JS before 与新 M35 不同，原样覆盖会退回旧结构。新文案由 M38 owner 依据新 M35 移植原中文 delta，新的两组有序 SHA 固化于 `deploy/ui_wording_manifest.json`；另外三组未变。

v3 增加显式 `--onboarding-commit`，必须与 `--localization-commit` 指向同一审定 M39（词典与 Framework 翻译一起交付）。CRM 保原55来源/守卫，Framework 只接受 `apps/frappe` 根下三个独立 SFC：GettingStartedBanner、HelpModal、OnboardingSteps。准备和最终 guard 校验独立根、明确三目标 before/after；只复制补丁脚本，不整目录覆盖 Framework。构建先核原 Framework before，再执行原生补丁 check/apply/verify，最后在资产构建前后核 after。灰按钮与本地化在同一 Banner after，禁止另叠样式补丁。

M35 新增 `apps/team_access/team_access/public/access.js` 为第九件最终有效覆盖（两处样式，JS 权限行为不变）；根/sites 同名静态文件继续强核。新 CSS SHA `058c3019494b3718d129c2a2e4616663d934b96d4c8036de409f7d11a93578cb`，UserDropdown after `5d6ac5cadd8248880ed1e0b124f971271147d898d5869117a24fc88c9c652aa6` 均由新 dark-ui manifest 读取，不沿用首轮哈希。原 M24/M30 manifest、安全边界、legal 和认证不变。

v3 仍使用原两层 caf102 基底执行一次集中标准构建，不从已叠 UI 镜像反复累加；原所有容器/卷及配置受保护。只回归本次实际改动覆盖的日程、access、M39翻译/Framework SFC；不重复已绿未受影响的 native326 或后端权限/恢复矩阵。以下结果待实际执行追加；本段不宣已构建/已部署。

### v3 真实构建、首 runner 失败及同镜像定向续验

精确集成源码 `073d0f23ee8ff8e2eb103296a837cc6541ec4d51`，context `deploy/.runtime/ui-3e8c9c113a1046aa93cd800cb3a32045`，receipt `c71459eddbdc0967825e26e607f90888b5634a1c44fd483e99589de44c3b815e`；六项组合离线测试 PASS，实跑三个 Framework SFC before→check/apply/verify→after、漂移及重复应用拒绝，CRM55来源/守卫、五新 wording 覆盖与原布局衔接通过。未重复未变品牌六项或其他无关矩阵。

`bash-ivp52qpz` / Windows PID28716 **82.870秒、exit1**：其中唯一标准构建**实际 exit0**，新资产 build/source/Framework after 均通过；随后定向测试 **Node34/35**，首失败 `ENOENT /tmp/u030-contract/apps/team_access/team_access/public/access.js`。原因是新增样式测试读取该临时文件，而本轮 runner 把实际 artifact access.js 的复制放在 Node 之后；原 image source/asset SHA guard 已真实通过，不能归为产品源丢失。后续静态/Framework runtime 尚未跑，原 report/log/退出1 probe 保留，不倒改为全绿。

只新建 runner 版本，把实际 access.js/page.js 提前复制 `/tmp`；没有改生产、测试断言或白名单，没有重新构建。`bash-nghk964i` / Windows PID4508 **46.687秒、exit0**，复用同一新镜像与本次已建两个卷为只读，read-only root + `/tmp` tmpfs/none/restartno，仅续定向合同：

- 日程两个既有 Node suite **35/35 PASS**，含新 access 注入配色/路由/observer 去重、新日轴位置与原功能场景。
- Python 静态 **5/5 PASS**，包含新 timeline→options→editor 真实 DOM 次序、原 ID 保留、默认折叠和不缩字号。只读旧公开 HTML fixture 替代测试内的 `git show` 输入，不改变断言或实际生产源码。
- 实际 page.js 既有 DOM/fetch 受控合同 PASS；真实 CSRF/session/持久化仍归浏览器/既有后端证据，不外推。
- M39 三个实际 Framework SFC 的 Vue parse/compileScript/compileTemplate、CRM 翻译接线、中英/服务端法语欢迎/进度表达式、按钮回调合同 PASS。
- 实际 M39 更新词典的占位符、locale、context、服务端优先级 PASS；来源/双静态 guard 及 **78 个 HTML 静态引用**均通过。
- 本轮按约定不重 native326、原 SFC、后端权限或恢复矩阵；这些代码未改，首轮对应证据只作历史，不伪造本轮重跑。

最新候选（非线上）：

| 身份 | 值 |
|---|---|
| tag | `crm-local:ui-3e8c9c113a1046aa93cd800cb3a32045` |
| index | `sha256:6d14300937ea0bc818c400525138f7e21086236df074ba0c9b785a3ad0bd303d` |
| linux/amd64 manifest | `sha256:7fa4ede1acf5d939679dc89602c27be7b0e1c2dd789ec25232f2e3429bcaaec6` |
| config | `sha256:ee6116d442e156a9071aac570d9f9dea28bdc383a245d5782e3625fcaf700075` |
| 层数 | **7**，原 Config 除明确 UI labels 外逐值相等 caf102 |

首次构建窗保护原159容器/128卷，七guard通过，仅新增退出1测试probe及两个自有匿名卷；续验保护原160容器/130卷，六guard通过，只新增退出0非OOM probe `ab039b663d2c312b50de615db64ffb90250b132e9b451c215134788072e86223`，复用原本次两卷只读无新卷。daemon 与主 image lock 保持，无新业务运行、站点/数据/权限修改或 SSH。两阶段都无 final guard failure。第一 Ubuntu 已明确释放给 M9，由其复用已存在 M32 与 SHORT/OVERLAP 夹具做集中视觉复验；M37不再环境操作，无后台。

完整旧失败 `deploy/.runtime/u030-v3-83ea2c14c5df4275ad549fc949a85b5c/result.json` SHA `bc7a543c2d7359d30529a3cd7c9a5a3c8d803226e15745c5baa13a5c7545b7c3`；成功 build log SHA `815ea85f1241c0abdeb1f95ebac3ac9405acceeb011ab85b8d1b0fe5b9229e26`。新续验 `deploy/.runtime/u030-v3-resume-e29a0407b9bc452fba766f384aeaf1bd/result.json` SHA `70afd8c7ac0870247a68697bb74c240633f0f151921ef25d6bfcb136bcf2a95e`，`concentrated-targeted.log` SHA `44a3e1b19c606b53e44d24387f4a3fcd59dade03c5a6356a0019e4d0f126bc1c`；同目录 `static-receipt.json` SHA **`62d25c8126d7e6667088bcd934bd87ee77b256b9f1c80ccbda4249cc0d878111`**。

| 最新静态 URL | SHA256 |
|---|---|
| `/assets/crm/frontend/assets/index-BDrf0DB4.js` | `2c12cdf7f20515a160cf58615e01a528b40d823eb01f9e32181ad1d430a7ec3e` |
| `/assets/crm/frontend/assets/index-CkYIMfiN.css` | `d56439b25f3b047cf85706c48ddccc97933df98d8f32a3de993e62510db48ca6` |
| `/assets/team_access/access.js` | `3f366ec57cdbf7be911a80d7e3a634964d29bd0adbad536d70659418a01be34c` |
| `/assets/team_access/page.js` | `188a4163fdeb7173b4c7a0f08cc9948c2c8ad9f7edc722fdab4535b3edb49931` |
| `/assets/team_schedule/crm-theme.css` | `058c3019494b3718d129c2a2e4616663d934b96d4c8036de409f7d11a93578cb` |
| `/assets/team_schedule/team-schedule.js` | `b416b3adbd39a6235fe0f3b847a3bd47b1a5df16499a020a8fb4bff934f5b8ba` |
| `/assets/team_schedule/team-schedule.css` | `23e1e6673b8f8d0bba20c29fe8f85ef5d9ae9a14375c994250d5984ffc64b75b` |

login CSS、standalone词典与 PWA 名称资产和首轮表中相同；完整十件 URL/bytes/SHA 都在新 receipt。框架本次变更三件来源后哈希见 M39 manifest，源码守卫在真实 build 和最终测试前后核过，不把文件编译等同页面视觉。仍待 Terra 实际 1280 首屏截图/引导中文/标记和私域按钮对比度复验；已有正常核心场景不重新扩矩阵，线上未动。

## 二轮实拍后接线修复（v4，源码待审）

二轮窗口按 fixed deadline 收尾与资源恢复 PASS，**Terra 正常注销未确认**；运维检查器自己的登录/注销成功不能替代 Terra 浏览器末态。二轮截图证明侧栏自有标记与步骤中文已生效，但 HelpModal 欢迎仍旧产品名/紫 logo、右下入口仍白底浅字，不能因十资产 GET SHA 通过就宣浏览器执行链正确。

只读源码诊断确认 HelpModal 是另一品牌调用路径：M24/M30 后 AppSidebar 明确 `:logo="CRMLogo"`，且不传 title，Framework 再取默认 `Frappe CRM`。M39 对标题调用 translate，但原生服务端同键优先，具体窗口的 server 字典值未采到；右下独立脚本走 after_request 注入的固定 URL，旧节点/缓存/important cascade 的现场原因也未证。后继不把缓存当已确认根因，不以这些未知为由改全局词典或权限。

本轮最小确定性接线：

- branding 增加 AppSidebar 有序修改：before 严锁 M24→M30 后 `e169f9d13cec9245390a8854b1dba8026227945abcaac03fb097473fca29a852`，after `96633536c614db3655dfd4109525f8f21e5ab927c77a7ddebce1f9547095a75a`，仅将 HelpModal logo 改为自有中性组件并显式传 `title="哲人石CRM"`。不再以旧产品名翻译键决定欢迎品牌。原导航、权限/恢复事件和 telemetry 回调保持原字节，Framework 默认值/上游版权不改。
- 新 `PhilosopherLogo.vue` 是中性轮廓与三色点标记，不修改上游 `CRMLogo.vue` 或用户自定义 logo。
- `branding/access_version.py` 从**最终导出的 access.js 原始字节**生成完整 SHA256 query URL和 request before/after receipt。仅对固定基底 request.py 的一处 script tag URL加 `?v=<实际内容SHA>`，不动 after_request 清洗、响应状态判断、Cache-Control、认证、权限或 CSP 行为。源码不直接编辑 app；构建在最终 M35 access.js 覆盖后，严格 check→apply→verify，最终 guard 同时核 request 后态、实际 source/asset 摘要。此是更新保障，不是缓存故障已证声明。
- M35 `fc25460a6252c91c7c123107b8e7e5a2188afad9` 负责 owned 旧节点幂等样式刷新及短事件编号/同轴侧栏；M38 `949838997e9d63ac98e36064d10d16ee87ddb62a` 仅将原中文 delta 衔接至新 rail。两者已审，不复制回旧 c558 文件。最终 access 字节预计 SHA `7d26cdb3a226da9094e9e2f7ed5b1aadef2790de46fc0c3d47fea244bee043d6`，preparer仍实算并比较，不以说明里的预计值代替生成。

验证包括实际 after_request AST 的 script URL、sanitize调用/状态/缓存头不变、重复不加tag、asset字节变则URL变、未知request/asset拒绝；CRM branding有序逆变换等原e169、品牌标题不引用旧key、原导航事件保留。旧节点测试只运行 M35 已有明确用例，不扩全矩阵。冻结 tip、实测数及新context待随后记录；当前尚未构建或部署这轮源码。

### v4 接线冻结与定向结果

生产新接线冻结 `894934e`，随后 `b0ef5dbfe5c17d0ae5d5a6dee67c6ef0da270a13` 仅修离线 fixture 的 `PATCHES` 临时根绑定。初组合因 fixture 沿用 `/home/frappe/u030` 常量报两处路径错误（未到实际代码替换），已修测试根而非放宽生产 guard；后六项组合全部通过。品牌7项、实际注入 AST/摘要2项、组合6项与 M35 既有 owned旧节点样式定向1项均 PASS，没有重旧无关矩阵。

准备 context `deploy/.runtime/ui-922ba2dbf7c8479f8054c5ba951caa24`，receipt `5f463ef6a931a2ae2b365bec74899ed2121fac7cb146d00c343a5841ebbfdc9a`，应用输入为已审 M35 fc25460/M38 9498389/M39 23a36d6。CRM最终来源/守卫56项，Framework3项保持；新增request独立校验不混入CRM根。

准备器由最终 access 字节实算出的 URL：`/assets/team_access/access.js?v=7d26cdb3a226da9094e9e2f7ed5b1aadef2790de46fc0c3d47fea244bee043d6`；request before `0a654aaeba6e9145bc0bf35b9ccd1f07033038df9fc3926e6cda53e34522331f`，本次生成 after `bd6ba3cad3290549b8d028ea868cd72e2cc3543a4b3978145ffd509deb30d3bf`。换任何最终脚本字节，query/after随之变化，receipt漂移或实际asset不等即拒绝。这个状态只是源码/定向合同已验、已交独审；未运行本批标准构建、实际HTTP或浏览器，不把资源版本化当已证缓存根因或已证现场颜色修复。

### v4 审定后唯一标准构建与实际改动产物验证

Sol对精确 `920d65f28b79d9c3b6bc78ceffa4e91adee45015` clean/hold（无finding，保留门为构建/真实视觉）后，tower明确放行一次第一Ubuntu构建。锁 M35 fc25460/M38 9498389/M39 23a36d6，不重旧候选。新 context `deploy/.runtime/ui-6392048dfa0e42e0b8e9c8b51d880076`，manifest receipt **`a84d623df4bdbf9145bea4451c3afc3bf3105ddb51d3815fd374221a8903609a`**。

唯一 `bash-qfj054jl` / Windows PID55512 **86.823秒、exit0**，标准build与随后改动产物测试均实际exit0。CRM Vite 7.33秒；不重native326、旧SFC或权限/恢复矩阵。

| 最新候选身份 | 值 |
|---|---|
| tag | `crm-local:ui-6392048dfa0e42e0b8e9c8b51d880076` |
| index | `sha256:2aa73e9b44d7d4919e41f6288f00e0285a2bd0eaf4b95db1e214b01a8f7fcb5f` |
| linux/amd64 manifest | `sha256:596329ca0b2376f6d47a9c3172c0a08a6ce4cc09fc1501f9a5783ff961d71752` |
| config | `sha256:490fbf8f22032eec418a702bd790d8661c725b5749afbea2e960214529bf4abb` |
| 层数 | **7**，原运行Config除新增明确UI provenance labels外逐值等父 |

实际最终镜像测试通过：日程Node **36/36**（包含同轴短事件编号/rail、owned旧节点幂等样式合同）、静态 **5/5**、实际AppSidebar与PhilosopherLogo SFC编译/固定品牌title/原导航与身份guard、实际request.py的after_request AST注入URL/sanitize调用/状态/缓存头不变、实际access.js源与根/sites两asset同SHA、Framework三SFC编译/回调/语言、既有locale/占位符/服务端优先合同。前后 CRM56来源/守卫、Framework3、原M24/M30及全部映射/资产实物通过。

`request.py`真实after为 `bd6ba3cad3290549b8d028ea868cd72e2cc3543a4b3978145ffd509deb30d3bf`；测试执行实际after_request函数而非重新手写注入替身，得到 `/assets/team_access/access.js?v=7d26cdb3a226da9094e9e2f7ed5b1aadef2790de46fc0c3d47fea244bee043d6`。这仍是产物合同，不声称已采现场浏览器执行/颜色；后继M9正常HTTP/视觉应核实际CRM response含此URL与query GET摘要，不能只核裸asset。

原 **166容器/130卷**、daemon与主image lock的8守卫保持，只新增退出0非OOM probe `5f365dfdd04d336b96d380e8096a07734bd2ec50ec22921af1e5a183d9e2cb1e` 及两自有匿名卷（保留）；没有站点/配置/业务/线上/SSH操作。第一Ubuntu已明确ENV RELEASED给M9，无后台。

报告目录 `deploy/.runtime/u030-v4-7c8c9619fe3a4b318d9cac4ba887d5b3/`：

- `result.json` SHA `c8bab66059106bdaf88e2e222d8f0b2ac8fdda84c45ba85f7bab87fb3e992b10`
- `standard-build.log` SHA `12c4edd01c38bf048097c335ebc526fe55a793956284a3f8d78fe3dee676b2fc`
- `changed-artifact-targeted.log` SHA `61fdb5bf7cedcb4665758af9f82a70c60144958e5c7ed4729b214785a07f1471`
- **`static-receipt.json` SHA `c98af659d4590af142e91bc5697724d5382852867b6028f8129cf8f4b863b419`**：重点11URL与 `all_dynamic_assets` **201条URL**（全部生成CRM JS/CSS/webmanifest、HTML引用及版本query的bytes/SHA），供后继准备核对；不是201个HTTP请求已实测。

关键新资源为 index-BROohc0i.js SHA `b429be037f62b42b915c27b90c02c7a118909ad53ba095941ecf186127607b9f`、同index-CkYIMfiN.css SHA `d56439b25f3b047cf85706c48ddccc97933df98d8f32a3de993e62510db48ca6`、新日程JS SHA `f2d02bb258cf3216887dfd96df52a2d64c12db6e611e787912166f19f0bd3caa`、日程CSS SHA `a8bd305e20e8f86e8a15c605cc6eb4ab4f97ff23219f22ddeec9fb6e3b5afffe`，完整动态URL不要从旧receipt猜文件名。

后继交M9同M32定点视觉，不自行开站。准备阶段与有效验收计时分离，准备完成**立即READY通知tower/Terra**；若采用固定总截止则尽早READY，不事后延deadline补时间。二轮Terra正常logout仍未确认，运维固定截止恢复PASS不代替浏览器logout证据。最终HelpModal品牌/同轴标签/入口颜色实拍与实际版本URL执行仍须后继真实短测，当前未Complete/未线上。

## 独立页CSS-only审定增量（构建前）

M35 `2ce92464b695e0330d75e9b91932ef70e0cadde1` 已获Sol clean/merge，tower授权一次最小候选构建。canonical/payload精确新SHA `a80f2861ad92a100743a5ffed19d0f4c20c96374bad3cdec18ebb6715b8c9d71`，仅活动路由Framework palette/nav和独立页标题浅字规则。M37已逐Gitblob核对该提交相对fc25460的五项文案生产前驱、access7d26字节、App/index/UserDropdown三个patch合同全等；因此仅将有序wording contract的base_revision登记为新精确dark commit，五组before/after不变，M38仍用9498389，不另造文案replay或退回rail。

本轮保审定920d品牌/request接线生产字节和M39 23a，原43/nav及全部guard不放宽。标准build后只验证CSS受影响两项既有静态合同、最终source/asset guard与完整动态receipt；不重Node36/native326/权限或恢复矩阵。v4真实CRM/日轴截图已由Terra完成；其正常logout由M9最新收窗消息确认（13:29:33Z），仅用于v4那一窗，不能追改此前第二窗注销未知。下一窗口只活动页及登录必要视觉，READY与计时规则保持。当前未构建本CSS候选，以下证据待追加。

### CSS-only候选构建与交付材料

精确集成登记提交 `9e8b82f`（仅两个base_revision精确常量及说明，原920d品牌/request逻辑不变），M35 2ce9246/M39 23a/M38 9498389。context `deploy/.runtime/ui-ebc790fba433470789113948e69f50fd`，receipt **`b79b28749c00e44c6dbeb010f28f2e30b22a446f7a4a015f256ab5304385eae3`**。准备器对五文案新dark前驱逐字节核同原before，未跳哈希或要求文案owner无意义replay。

唯一 `bash-iibj6zya` / Windows PID52924 **85.307秒、exit0**。标准CRM/access/schedule资产build实际0，Vite6.93秒；最终镜像复制真实生产字节执行两个已有CSS受影响合同（shared theme/catalog/raw option；Framework活动页route palette/nav/显式标题前景）**2/2 PASS**，前后来源与完整资产guard通过。没有重Node36/native326、旧核心UI或权限/恢复矩阵。

| 当前候选身份 | 值 |
|---|---|
| tag | `crm-local:ui-ebc790fba433470789113948e69f50fd` |
| index | `sha256:2f92c460d47948bf6f030e23b24687b82ca3a92c4af4b8a200da7de7ac97db1b` |
| linux/amd64 manifest | `sha256:00481a4d427e238f71e41e00338c36eb86f180132577f01913b2f3a822533753` |
| config | `sha256:50a654164666adafc4f35c7a14b950b13cfba43363ce977aaa315461a0fd7987` |
| 层数/运行Config | **7**；除预期provenance labels外原Config逐值保持 |

canonical/payload及根/sites共享主题最终SHA **`a80f2861ad92a100743a5ffed19d0f4c20c96374bad3cdec18ebb6715b8c9d71`**（7187B），原56CRM/Framework3/43nav、access版本7d26与request后态、标签rail及五文案守卫保持。新入口JS `/assets/crm/frontend/assets/index-1L7LpzFF.js` SHA `8a196fe0ea1df4f5fb5593fd5e11e441c9ebf29d3da6f3e0ba72d6f6306480e9`；CSS `/assets/crm/frontend/assets/index-BSWanVSZ.css` SHA `03755f815a2b02c796480d9d6575b629408aeed2971f66bb7f2e624439b8a150`。原脚本query完整URL仍为7d26，实际注入逻辑未改。

原 **174容器/132卷**、daemon与主锁八guard保持，仅新增退出0非OOM probe `36ac5464fbe163bafda4857c71be8f88a5d15b3f70dcdf1dbbc7f01a222b713b`及两个自有匿名卷（保留），无站点/业务写入、SSH或线上操作。无后台，第一Ubuntu明确ENV RELEASED已交tower/M9。

证据目录 `deploy/.runtime/u030-css-4bcbf9ec62e44c8c9d32154922c94b6e/`：

- `result.json` SHA `08b39ad8cb5dd50f6b0f5a9290a9e2862d2d8c80fd81011d37a76059f6987867`
- `standard-build.log` SHA `b37b76fa485db50380454882928452cb1e480bcc3057ac6e5cd1f7eb824ebf99`
- `css-only-targeted.log` SHA `1c045c1923bc1c14823b943181d03c17db4db824657b3cd3d2dbfc365ccaf1ac`
- **`static-receipt.json` SHA `bdf4c6827b194372ea600fc05a70750d47d4d42b1ac69f58f1f6792734f2bd1f`**，含201完整动态URL及11重点URL bytes/SHA（含实际access query），不是201条浏览器HTTP请求。

后继只活动页+登录必要视觉，复用M32和既有账号事件；已过CRM品牌/日轴不重整链。准备完成即READY，独立有效验收计时，不能事后延deadline。当前仅该CSS候选产物合同通过，活动页/navbar/标题/入口真实颜色与登录视觉仍待Terra；最终交付材料已具备来源/构建/测试/镜像/资产证据，但不在视觉通过前Complete或宣上线。

## 最终限定核心验收归档（不重采、不外推）

以下为 tower/Terra 已有工具引用，按候选分别记录；截图不是本worker重采。用户明确本轮不求所有风格完美，限定核心范围收口，不再循环登录截图或增加功能/矩阵。

| 候选/场景 | 精确已有引用 | 可成立结论及边界 |
|---|---|---|
| 最终2f92活动页 | `visual-855eae58-f73b-47ae-a807-9021709e59d3`，CSS1280×720 / 图片1600×900 scale1.25 | h1、Framework navbar、主体暗浅清楚可读；右下白底黑字可读，保留非阻断风格偏差，不说全部颜色符合设计 |
| 最终2f92正常注销→登录页 | `text-681b0099-abc2-4a61-ab03-4b5271b0482f` 成功提示；`text-c9a1d582-dbe8-4b89-89c0-68d6531eb2c7` /login | Terra正常退出已确认，不是仅期限收窗 |
| 最终2f92登录视觉 | 两次 `PAGE_NOT_READY`，无成功snapshotID | **登录截图未验**，不虚构图片/ID、不写视觉通过；正常表单登录/身份/退出已有独立真实证据，不再循环截图 |
| v4(2aa73)真实日轴 | `visual-4c3acd4f-1d42-4a6f-aecb-b1132b1a0c83` | 同屏轨道、编号1/2连接线及右rail完整标题/起止/状态无遮挡可读 |
| v4 CRM品牌/引导/入口 | `visual-45d4eb7d-7d9a-4e3a-be4e-8d0f5ef3000a` | 哲人石CRM品牌、中性logo、引导中文与入口正常显示，不把此前残留截图当本候选最终表现 |
| v4创建窗文案/提示 | `visual-33389130-7c4c-4922-8b9a-ed2e15cd98cd` | 中文公司介绍、深底提示细金边可读；该窗未提交，不当新增业务成功 |
| v4退出/login | `text-361b0be6-414f-4b0a-a07f-9e00f1387341` | 对应v4正常退出；M9收窗报告有明确browser release |
| 首轮d573 SHORT编辑 | `text-c1e669d5-da7a-4764-9475-5ab16a561c8e` | 编辑到revision2 |
| 首轮d573 OVERLAP创建/取消 | `text-ddb543dc-89d9-4c3a-9c10-cf1b87707b12` / `text-01a1d40b-e88d-4e9c-9c05-e3cb9f21a575` | 原核心创建、取消到revision2通过，非最终2f92重跑 |
| 首轮d573退出/后台清屏 | `text-d6ba3506-c247-45b6-bb64-4b4a0ec4d486` / `text-1b2b3622-12d1-46e3-8f75-2cd8bd3efd1f` | 对应首轮行为；不倒推每个后续候选都重跑 |
| 首轮d573 Lead00001创建/reload | tower/Terra原功能交接；具体创建/reload snapshotID未收到 | 只引用已交接结果，不猜ID、不把v4未提交创建窗当替代证据 |

继承边界：d573原主功能与后继未改的后端/原43+nav逻辑由逐来源守卫保护；v4改日轴可见标签与品牌接线后已独立截图/实际产物定向验证。2f92相对v4仅共享CSS有限变更（及由标准Vite重新生成资源标识），M37逐blob核App/UserDropdown/access7d26/标签rail/文案生产前驱不变，最终guard核后态，因此复用v4 CRM/日轴视觉及原核心功能证据，**不宣称所有操作均在2f92重做**。正常默认中文仅原生System Settings单字段，明确User.language/时区/请求偏好不被覆盖；多语言偏好整个浏览器矩阵未全面测，不泛化为全语言验收。

最终M9窗口 `m37-m32-ui-685a37e3a6e24dd6be22f265c2740ebc`：Terra正常logout后提前explicit browser release，14:32:01.181676Z恢复完成/exit0，15ops/33guards PASS，8094 Listen0，app3/relay停止，原en/UTC/assets156/sitecommonSHA/infra原停状态复原，原六卷/testapp/keys/账号与合成fixture保留。报告 `P:/CRM/.tower/worktrees/wt-9/deploy/.runtime/m37-m32-ui-685a37e3a6e24dd6be22f265c2740ebc/result.json` SHA `af5126fa85ae96ecd0dd77a3efb7f959f95181b696b5d849f8fc910127bf1783`；同目录Windows proof SHA `6b91493c5cf343feac0812d0d8a63d9e4cb7b97c34c2291a1028ee130aa752ec`。Linux/Windows11资产、实际CRM query注入及完整query响应SHA、普通账号登录/活动入口/退出已实证。未SSH/线上/重建或重矩阵。

按用户限定核心范围，任务2的品牌/title/apple/lang/原生login接入与任务4的审定组合构建/必要回归/Terra核心短测可准确收口；**登录视觉未取得、右下入口风格偏差、多语言全矩阵未全面测**为交付限制而非假通过。没有未解决的正常核心功能失败，不新增无限截图门。最终completed只为请求独审，非已merge/已上线。

## 最终镜像归档与部署owner交接

先查本worktree和M9现存材料，确认没有2f92 export；M9各UI窗没有save/export/build，旧caf父tar仅作七字段格式参考。收到M9明确ENV RELEASED后，唯一 `bash-cbd8hvju` / Windows PID33516 **87.458秒、exit0**，只 `docker image save` 已受测2f92及运行原242161归档验证器；不重build、不创建容器/卷或启动站点。

冻结目录（ignored，不进Git）：

`P:/CRM/.tower/worktrees/wt-37/deploy/.runtime/u030-final-2f92c460-release/`

| 材料 | bytes / SHA256 |
|---|---|
| `image.tar` | **1540059136 bytes** / `0deba5793481799ae1774d37926def678f35d8a1372eadaf09e31d55a144ccae` |
| `release.env` | 七字段 / `6a961af6a88356b529e34310559ee07beb09df57bf56de81cf6e8600710b9453` |
| `image-rootfs-layers.txt` | 七个有序diff_id / `225d78e8eee4dea16a4613ac2ea372dcf288e6d2ca2f75c2ce4822a5f7a98e33` |
| `candidate-manifest.json` | `6184ff568ed0722b47d4399bcd64ba9f04acd5904930c0ec0cc3cfca864f8292` |
| `export-result.json` | `ab82cc45771a40d1da4d56380e1dc2b6c35f2766277748a30f684f18aa5334d8` |

release身份为当前已测 index2f92/platform00481/config50a654，不是旧caf父包；resource_import/team_access/upstream字段按实际继承labels取值。**team_access label表示已核继承基线531，不掩盖request.py存在明确branding URL增量**，最终manifest另列完整UI revisions/source receipt，禁止把该label解读为整个app零修改。

原 `P:/CRM/.tower/worktrees/wt-9/deploy/.runtime/m9-maintenance-242161-r7/deploy/remote/verify_image_archive.py` SHA `ac13f1f9dfecc21eb6cc6df06ae1471f0d4aa20645a9eab9906c478b992b1b4a` 未修改，实际exit0核全部blobSHA、index→唯一linux/amd64manifest→config，以及逐gzip解压diff_id与七层清单/config全等。另读归档config与受测docker inspect的完整Config逐值等、RootFS七项有序等。不是只核tar大小、标签或版本号；本机save/verify不代表已远端load。

原180容器/134卷、daemon与主image lock六guard保持，无新增资源，无后台。第一Ubuntu已明确ENV RELEASED给tower/M9。所有旧候选/失败日志/备份/卷保留，不做prune或清理；本包SHA/receipt交远端部署owner `remote-usable-baseline`，此交接**不授权其SSH/上传/部署**，正式发布仍由tower另开维护窗口。

### 默认中文的可逆原生设置

在后续明确授权的部署窗口，先只读记录本站 `System Settings.language` 原值，核真实语言码Chinese为`zh`，通过原生System Settings表单（或同等正常DocType保存）**仅设置该字段**；保存并按既有受审流程失效本站必要网页/设置缓存，使新请求生效，不flushdb、不清所有session。若需回退，仅恢复刚记录的原language值，不把本站历史时区/业务数据恢复混为一谈。

不得批量覆盖 `User.language`，也不改 `time_zone`、cookie、请求 `_lang` 或 `Accept-Language`。明确用户语言仍按Frappe原生优先级，高于站点默认；Guest浏览器明确其他语言可优先，不用before_request强制中文。没有language记录的用户才使用默认fallback；此步骤不修改认证/角色/数据权限。M32各验收窗已仅临时默认zh、原User语言和UTC保持，退出时恢复en；不能把M32临时设置误称目标线上已改。

### 最终交审状态

实现、精确组合构建、低层归档、必要回归及限定核心Terra验收材料已齐；任务2/4按上述范围收口。真实未验登录截图/可读非阻断入口风格偏差/未全面多语言矩阵/未远端部署保留为限制，不假通过、不以新测试无限延长。当前没有新的必须交用户决定的产品价值卡点。TowerComplete仅请求最终独审与合并，不代表正式发布已完成。

## M42 常用界面漏译后续接入（准备阶段）

M37按后续授权恢复active；本轮不新增功能/本地站点或浏览器，只准备常用界面翻译的严格增量。M42最终冻结输入 `95e5ce6f7b967c62761fb06e61baf90ce3d110ae` 待Sol独审，目标实际为四件（含后加的Check Filter显示接线），不能按早期三目标遗漏：Notifications.vue、Activities/DataFields.vue、Filter.vue、IconPicker.vue。完整before/after以独立common-ui-localization manifest为准。

已从本轮保存的**实际已上线2f92归档**选择性提取四SFC，逐个SHA与M42 before全部相符（不是只核master或模拟HEAD）；只公开源码，无sites/凭据。旧catalog SHA `ea598fe9e1b8c7a10ddd57e8c35950c30bc8462fe1e12ae3f3b2cbe6a8f6b551`，新冻结catalog SHA `f07c9e466f23dbe2847c9549a4e35f7c645e2ae9d01e1b9a66761aef9fabdbc5`（取代早期候选71d7，不使用未冻结值）。原词条必须逐值保留，不能借字典升级覆盖M39已审术语。

新增独立 `prepare_common_ui.py` / `Dockerfile.common-ui` / `verify_common_ui.py` / `check_common_ui.py`：固定FROM已上线2f92 tag，构建前必须核精确image2f92/config50a654与原七层，不依赖浮动tag。有限COPY仅common-ui apply/manifest、新catalog/manifest和独立guard，不整app覆盖，不重放原dark/localization/branding/onboarding/wording patch。原/home/frappe/u030完整最终guard前置通过；四SFC独立check/apply/verify，旧catalog按精确ea598→新after应用（当前translation/crm.py已在已上线后态，不能重新套原始before），并拒绝任何既有key值变更。

最终增量guard完整重建原五app/source、M35/M38/M39、品牌56/Framework3/request版本后态预期，只显式覆四新SFC和catalog；原Framework32映射、所有standalone资产保持。仅标准 `bench build --app crm`，不重326或权限/恢复矩阵。候选Config仅新增commonUI来源labels、RootFS前七层必须等父且总层数≤16。实际build/测试仍等待M42审定，本段不宣通过。

M43独占修改deploy/remote/trial.sh以保持HTTPS/socket配置，M37本轮不改该文件或其他远端流程。后继部署必须引用M43新审定工具来源，不误标仍是原242161；镜像归档验证合同不变。最终由M17真实服务器部署后Terra在HTTPS相关入口短验，不启动本地浏览器/站点。

### M42首次标准路径首异常与最小修正

接入源码 `6c8a9d1` 已获独审clean/hold（无finding，hold是产物/部署/HTTPS短验门）。首实际build `bash-nn5bi7ca` **31.778秒exit1**：原2f92完整guard、四SFCcheck/apply/verify、catalog迁移均通过，随后输入guard按manifest读取`/home/frappe/common-ui/deploy/...`，但Dockerfile将verifier扁平复制到了common-ui根，缺deploy目录而失败。**尚未bench/Vite或产候选/probe**，原finally资源守卫保持，旧失败不抹除。

只修标准COPY布局：三件已白名单deploy文件按原相对路径精确复制到`common-ui/deploy/`，所有命令也引用相同路径，补明确布局合同测试；没有跳输入SHA检查、改M42源码/词典或扩大目标集合。后续新context重试同一范围，不能把这个集成路径故障当M42翻译缺陷。

### M42实际增量构建/产物验证（部署前）

最小COPY修正提交 `0efd1fc`，新context `deploy/.runtime/common-ui-3c8a0ee657aa461d8d4f617807a5bf10`，receipt **`82d57798608695e07b64cf5ce6c6e06011ef602e13877df5584a496f4c4bedd1`**。M42精确95e5ce6已Sol clean/hold并准构建；M37初始接入6c8a9d1也独审无finding。四项离线合同PASS，新增精确COPY路径检查覆盖首失败缺口；旧失败context/log保留。

`bash-hrf96su3` / Windows PID46552 **54.728秒、exit0**，标准CRM build实际0（Vite6.90秒），最终产物实际四SFC parse/compileScript/compileTemplate、通知正文sanitize仍在、静态标签翻译、Check显示翻译且raw value仍Yes/No、locale/服务端同键优先与原占位符合同全部PASS。最终继承五app/M35/M38/M39/品牌/Framework3/request版本/source与所有standalone资产/Framework映射守卫通过；只四SFC+catalog显式变化。没有Node36/native326/权限恢复矩阵、本地浏览器或站点。

新镜像 `crm-local:common-ui-3c8a0ee657aa461d8d4f617807a5bf10`：index `sha256:35d0b0bd36ae08fa9d434b4275cb50bc4e202607c5f8ad95a34e6441c4922101`，platform `sha256:bd67dae52b227ad19e70f2ce4a20e18c89e40465106369a08c52cf638ea31b62`，config `sha256:310b0d22992ac555ea577f2fdc770f9adc0e21191d9d7e1855c6edd2d230649d`。**13层**，前七个diff_id与已上线2f92逐项等，完整Config仅新增commonUI三来源labels，无daemon/网络/依赖或权限修改。

原180容器/134卷及daemon/mainlock八guard保持；仅新none/restartno probe `2e5b75054fd9c64a5ee4eb4ed12d1185ae33875a4ea597ce02ce9c1575403dd2` 退出0非OOM与两个自有匿名卷保留，未业务运行。结果 `deploy/.runtime/common-ui-build-r2-b7b7ba02eddc4a5aa0db6e844e9656ea/result.json` SHA `f0378a871cf61a491b29f14edd320ad03289488656db9ae3d8ed26f5dece2d9c`；build log SHA `519cec4d13c0df887ff2b473e7cf3f0285fbf3a8668ba1fcec027410e54a66d7`；artifact log SHA `11548f58105c6712a71bd9a164ca50cfd6504be86483ca533e23238151d38894`。

同目录 `static-receipt.json` SHA **`6f87b250a4ab3a5cf282e7b7b349ff9f3325d93dc9425b5289641724bb530856`**，201条动态URL/11重点asset；新入口 `/assets/crm/frontend/assets/index-DO9vnRFq.js` SHA `f2f4adbae397d35bb4b28f71c03d9cce800b0652e3edcdf0b253504acec4fc54`（598675B），CSS index-BSWanVSZ保持原SHA03755f81。其余共享主题/rail/access版本与独立页资产不变。此为产物测试，不当通知/搜索/筛选实际HTTPS用户界面已验，等待M17真实部署后Terra定点短验。

### M42统一交付包与环境释放（未部署）

tower在源码/接入审clean后明确授权导出。本轮构建产物测试通过后，只保存同一新镜像，不重build。`bash-wloosn2g` / Windows PID71980 **86.088秒exit0**：标准save、原归档验证器全blob/index→唯一amd64manifest→config/逐gzip解压13diff_id、归档完整Config与受测inspect一致均PASS。

冻结目录：`P:/CRM/.tower/worktrees/wt-37/deploy/.runtime/common-ui-final-35d0b0bd-release/`

| 文件 | bytes / SHA256 |
|---|---|
| `image.tar` | **1548928000 bytes** / `45db442cc3c1614fcc8cafe9d56960fc22199f7d88b1ebcfc3ec6ce24eb39fe9` |
| `release.env` | 七字段 / `dac7d52073d4252a4e42960860a3fa73f6241c2a5064a382e42eb7a0e8af6fe1` |
| `image-rootfs-layers.txt` | 13有序diff_id / `f3ec8f1e58f827572bbf1c3a0753c64080de2b75e7b588b61a5fe1d87a6622b4` |
| `candidate-manifest.json` | `98a93883e0998cc65a32022a7fb0f9486f245253536b6e23d8a2b23c039b7204` |
| `export-result.json` | `a3dc655c1cf9f8d6805e64ee00b6044c56c69a859d586b89491bb957a909c534` |

manifest明确parent2f92、commonUI95e5ce6/integration0efd1fc、来源receipt82d57798、static receipt6f87b250、未部署/HTTPS目标短验待做，不复用旧2f92 digest冒充新包。原181容器/136卷、daemon/mainlock六guard保持，无新资源；唯一新增测试probe与其两卷来自此前build验证，退出0并保留。所有本轮环境任务已结束，第一Ubuntu已明确ENV RELEASED给tower/M9，无后台。

新包与201URL receipt已直接交M17部署owner，部署必须按tower后续窗口与M43独审新工具执行以保HTTPS/socket overlay；原242161仅归档verifier出处，不冒称仍是未修改部署工具。M37本轮无SSH/上传/目标服务器操作，本地未启浏览器/站点；M17部署后由Terra在真实HTTPS仅通知/相关常用入口短验，未验前不宣全站汉化或本轮目标UI通过。原默认zh/显式用户语言优先和2f92既有限制继续保留，不为本轮再次改DB/重矩阵。

## Filter后态补修与临时只读失败分类集中准备

按tower后续授权恢复M37，当前线上基底35d0/config310b，不重放原common-ui或full43apply。M42已审 `3bcad3233cf674a145d47cbe3c927ff9eb432743` 仅Filter已部署后态4a502→82da91和catalog f07c→7f305；旧三SFC after保持。独立`apply_filter_label_delta.py`核35d0前驱，离线仅唯一逆转既有Check显示行并核原upstream2151，再调用M42已审transform生成最终82da；在实际bench仅写Filter/catalog两个明确目标，全部旧key值保持。未知源/临时冲突/重复拒绝，替换失败尝试回滚原字节。已从存档35d0 tar抽原字节做3项定向测试PASS，不以原apply重套已patch文件。

真实两次leads→筛选字段→任务都出现ACCESS_UNCONFIRMED，已有get_data499且无403；**根因未明，499不当权限失败证据**。M24作者实现临时默认关闭分类诊断，冻结 `d3e68f845d2bd71cbd375900ade70b9f3116916f` 待独审。M37从既有35d0受证归档只取三件公开源直接交作者：request752fdeb/frappeRequest83e4b44/ViewControls14383fb；根`deploy/.runtime/public-request-chain-35d0b0bd`，receipt6584a603c15a82760191fac0c06d5232cbe38226f54263b7a75eb227cd5304f7，无线上查询/环境操作。

本轮集中入口`prepare_concentrated_ui.py`/`Dockerfile.concentrated-ui`显式FROM13层35d0，保现有全部业务/品牌/主题/Framework/request守卫，仅M42两目标与M24四目标有界after。生成诊断四payload时从已知未patch公开utils源（request752f/frappeRequest5461）运行作者`source_edits.transform`并核最终manifest.after，另外两resources直接精确payload；不在运行镜像逆变换/重apply43。full43manifest只允许预定四条变化，其他39条字典相等，所有最终payload/source/hash都有receipt。`verify_read_diagnostic.py`check/apply/verify守护四部署before、回滚与最终after，不新增目标。

诊断源码默认关，prepare未显式flag时`diagnostics_enabled=false`；只有`--enable-read-failure-diagnostics`把冻结receipt设true，构建Vite进程`VITE_CRM_READ_FAILURE_DIAGNOSTICS=1`启用，不是运行containerenv/URL/storage开关。tower要求此次审后诊断候选显式1。分类只固定枚举/布尔/状态/耗时桶，WeakMap首条内存码由现有安全边界DOM展示，无message/stack/params/URL/身份，无外发/持久，原error/请求/拒绝状态及调用次数不变。M24负责采证后移除开关及四目标代码，按原四前驱恢复同时保M42新翻译/其他overlay；先off重建可停止采集/显示但不等于代码移除，不能整个回滚旧镜像丢新overlay。

当前仅源码接入准备，M24诊断独审前不build，不部署/浏览器/本地站点，不重326/权限矩阵；M43 HTTPS/OTA运维工具不改不覆盖。后续必须一次集中标准build与受影响实际产物定向，真实诊断码/根因尚无，不能宣修复导航失败。

### 集中准备的离线验证与诊断归属待修

准备接入提交 `1813b7d`：M42 Filter后态增量独立3tests PASS；从实际35d0归档四诊断前驱+Filter/catalog组合check/apply/verify的2tests PASS，原三commonSFC和未知源零写保持。旧诊断d3e68临时context `deploy/.runtime/concentrated-ui-fe87f705aca74bd2bc2ca625a1c37be3` receipt `139f944397eb4ae89a6120af31791bd4b23b2a4c8a0f0ec3be5ec3d349d98b26` 仅用于离线pre-review检查，显式enabled=true，**未构建/上线**。Windows既有Node22.20有`node:module.stripTypeScriptTypes`，未安装新依赖；实际镜像工具链仍须后继真实检查。

Sol诊断审seq147指出：仅比较generation会把已退休创建epoch的延迟请求错误标current，M24正按tower仅修诊断归属联合epoch（不改安全行为）并更新after。M37明确不以d3e68旧tip构建；等新tip/after窄审后重新冻结正式集中context，旧记录保留不擦除。到目前没有WSL/HTTP/浏览器/部署操作，没有真实诊断码或根因结论，不增加额外矩阵。

### 最终721集中候选：执行身份阻断、明确root授权与实际验证

最终诊断 `721155091b2cdcc672579b915f6178b374e05495` 修正current归属联合epoch，Sol clean/hold准临时构建；集中接入 `d1c298851cfecd7c0217af6841c8491ce41c950a` 也clean/hold。仅重新prepare最终输入，无产品接入代码改变或无意义提交：context `deploy/.runtime/concentrated-ui-12a16ee9a32b482b80e7b6d5e071c2f0`，receipt **`ca344b1fa9f73a158355eeac223529ad671e700fbcf866c6c0e5a9b31d1b1f86`**，显式diagnostics_enabled=true；原源码默认false不变。

首次授权流程在实际build前失败：默认wdd无Docker socket权限，原metadata.environment的docker ps即permission denied，operations空、未create/build/test；报告`concentrated-build-b81ee98a70bd4116907b5a7327d92aea/result.json`保留。只读身份核wdd不在docker组/socketroot:docker0660，历史成功35d0/2f92客户端相同Ubuntu默认用户选择、没有root参数，未推断组变化原因或自行提权。用户随后明确授权**仅Ubuntu-24.04本窗口以root执行构建与相关验证/归档**；不改用户组/socket/默认用户/daemon配置、不碰第二Ubuntu。M37才显式`wsl.exe -d Ubuntu-24.04 -u root`续同最终context，无重prepare/源码修改，metadata保护不绕过。

实际`bash-lu22g6vk` / Windows PID29088 **70.335秒exit0**，标准CRM build实际0（Vite7.09秒），完整继承source/asset guards保持。新临时候选：

| 身份 | 值 |
|---|---|
| tag | `crm-local:concentrated-ui-12a16ee9a32b482b80e7b6d5e071c2f0` |
| index | `sha256:59b37e9d855bc04b34412cae6b97feb17e69f2add8cbfd1eb55f94e03d18dd0b` |
| amd64 manifest | `sha256:83badb240f9871d2dc91b071e4f874322793ecc3af797c54bde6ebc04ed88ab7` |
| config | `sha256:2e14852fe01fc026abf25bd1689368bf45424a125eff74f4111b9ae18ed75806` |
| layers | **16**，前13项严格等35d0，完整运行Config仅新增focused provenance labels |

实际产物定向：原M24 active敏感失败分类/退休epoch两case **2/2 PASS**；原real-runtime末尾请求分类case独立入口 **1/1 PASS**（内部off/on各6情形，case body原字节SHA留存，仅必要header，未加载旧导航矩阵）；五实际文件（四新诊断+未变local.ts）逐SHA核后读取，现镜像Node`stripTypeScriptTypes`为function，未装依赖/替代API。实际browserEnvironment的off/on安全边界DOM文字读取有限D020102码、首码及敏感文本不泄漏合同PASS。Filter实际SFC编译/固定字段与用户自定义标签/rawvalue/其他Doctype runtime，以及原locale/占位符/server优先合同全部PASS。未326/权限恢复矩阵、本地站点/浏览器或部署。诊断VM使用原合成transport，不当真实失败根因已知；只证明临时码有界、保持原Error/安全行为，并可由内置browser读DOM。

原181容器/136卷、daemon/mainlock八guard保持，仅新none/restartno probe `47fd743fad012f82ae5ed6d3dcc68e7f5d40beb647ac4dae9312c104bda21c52`退出0非OOM及两个自有匿名卷保留。结果`deploy/.runtime/concentrated-build-2f88c509aa95409b81122d2595d37ee1/result.json` SHA `58af305cd6cfa5dd86f50d6918bf025bfabf9d7b89db45d64970592765060e17`；同目录`static-receipt.json` SHA **`31320de6032d13243f6c6524c0d67dd57a804f0faf7b8d8047da54a625597903`**，201动态URL/11重点asset，附diagnostic_temporary/enabled与实际五源SHA。新入口`index-DMxJXgQL.js` SHA `496b8da008d0cc5de5ff8c8203f4584550b1e1e7656e54e557c0618a0c64c85b`，CSS及全部独立页/品牌accessquery等原资产守卫保持。

本候选仅M42 Filter/catalog补修+显式启用临时诊断，**没有ACCESS_UNCONFIRMED真实根因或修复结论**。后继采证限已有安全边界DOM D020102固定码，不采message/stack/params/URL/身份或业务数据；M24采后负责移除四诊断目标及开关、保Filter/catalog和所有既有overlay。可先off重建停止采集显示，但不能当代码已移除，禁止整个回滚35d0丢M42。root授权只此窗口，原权限配置不变；归档后释放，不借此授权后续root/本地站点/线上操作。

### 临时候选59b37归档与root窗口释放

同一次明确root执行授权中，标准build/定向PASS后仅save同受测镜像，不重build。`bash-hoh6s093` / Windows PID45684 **111.498秒exit0**，原archive verifier全blob/index→唯一amd64manifest→config/逐gzip解压16diff_id、归档Config与受测inspect完整等值均PASS。182原容器/138卷、daemon/mainlock六guard保持，无新增export资源，无组/socket/默认用户/daemon配置改变。全部任务结束、无后台，第一Ubuntu明确ENV RELEASED给tower/M9，**本次root窗口授权到此结束**。

冻结目录：`P:/CRM/.tower/worktrees/wt-37/deploy/.runtime/concentrated-final-59b37e9d855b-release/`

| 文件 | bytes / SHA256 |
|---|---|
| `image.tar` | **1557855744 bytes** / `c8c7862da48fd9a0f14ed663777abd2cb6874b7053d14abba8bd6e46d6cd9367` |
| `release.env` | 七字段 / `120a2ee7d0be0f99ca7e8b41fd5cf0c55e30263e2e42456d9d6f7cfdf1f26d55` |
| `image-rootfs-layers.txt` | 16有序diff_id / `f70402777f7c19fc7c648d3fc102eeb815e4d67fe7ccc779e6f0c11daa9adf99` |
| `candidate-manifest.json` | `6863d6065b893dbafbd90ea01c82e2ba3968319bc3e15fac8baec4e1998ad871` |
| `export-result.json` | `53055783e5fd802ff4be9e299970c334daf91118356dbfcd1ef492765e9b4f14` |

manifest明确temporary、显式enabled1、原source switch默认off、721/3bc/d1c来源与ca344b receipt、root cause未知/未部署等限制。包与完整201URL receipt已直接交M17/tower，M17后继须按主控新授权及M43 HTTPS/OTA保持工具后态部署；M37没有SSH/浏览器/线上或本地站点，也没有采真实诊断code。定位后M24移除临时代码/开关责任继续，禁止whole旧镜像回滚丢Filter/catalog。当前交付的是有界采证候选，不是ACCESS_UNCONFIRMED问题修复验收。

## 锁页记录点3eee审定后集中候选（temporary）

旧59b37真实采码`FETCH/AbortError/current0`来自未导致锁页的旧catch，不能作为任务导航锁页根因。M24 `3eee6e217e838c950e8937c5a366908cf7323cd8` 仅将记录点移至原failed的ACCESS条件真正成立、current且尚未终锁分支，去除catch提前占首码；相对721只accountBoundary/resources后态变`f1bc6ff7...`/`c5774aa5...`，utils两件/原安全行为不变。seq150对精确3eee clean/hold无finding并准临时后继。这里仍非任务修复，也无新真实根因结论。

用户已明确持续限定授权：允许第一实验Ubuntu以root完成本导航故障收尾必要后继build/验证/清理，不改用户组/socket/默认用户/daemon配置、不碰第二Ubuntu，不扩至其他任务。M37在审定前只离线生成同现有机制context，接入产品d1c未变，没有为输入换tip制造提交。实际仍FROM原13层35d0+M42已审3bc，**不FROM16层59b37继续叠层**，Filter82da/catalog7f305和全部品牌/主题/M43运维工具后态保留。

context `deploy/.runtime/concentrated-ui-d3bb22dfc1d54da3b3d0c7dce2ddcaa8`，receipt **`5a392a6332024919e5c1823ec7a0c9e7512a281e0e576f823f181610c9eecc1b`**。显式`diagnostics_enabled=true`只供有限采证，源码默认关/采后移除责任保持。

唯一`bash-pcmr3hzv` / Windows PID56228 **69.648秒exit0**，标准CRMbuild实际0（Vite6.84秒），原active失败分类/退休请求2case PASS、3eee原末requestcase 1PASS（内部off/on各6形态，显式abort不占码NONE；body原字节留存）、actualbrowserEnvironment off/on通过真正failed锁页分支读DOM有限码，Filter实际编译/字段runtime/locale/完整继承sourceassetguards全部PASS。不再用721旧手动record DOM路径，未326/权限/恢复矩阵/本地站点/浏览器或线上。

| 新临时候选 | 精确值 |
|---|---|
| tag | `crm-local:concentrated-ui-d3bb22dfc1d54da3b3d0c7dce2ddcaa8` |
| index | `sha256:adddbb57d809f1e426b3396b99d8f797a6fd9b640ec3f27eb2b0abc7fd9624c0` |
| amd64manifest | `sha256:a3ac48e69b6590333b60e76306c10a2e88e086fd896416f844bf5c2ae32ca678` |
| config | `sha256:01971b83b27449e13e937c1e0518b9b0c18b466de64f3edc3e0a3d6a2322fb46` |
| layers | **16**，前13严格等35d0，完整Config除focusedlabels外保持 |

原182容器/138卷、daemon/mainlock八guard保持，只新增none/restartno退出0非OOM probe`c303f74dc70d27e9c48d0f314b122616020188a215ce4f728b7c17f0378c772d`及两自有匿名卷（保留）。结果`deploy/.runtime/lock-trigger-build-49979cc52fb541158e3187029337b084/result.json` SHA `e0bc1e4db08f17f7de308cd5aec9c88c7eb005a82820c0176d65d25363164398`；buildlogSHA `75b1ddae0002c300a0abdd01c618af6e646aaef5e0274f5a40635685a1d4e124`，artifactlogSHA `542a8425d96184ed05183849599be6b3c1518804002b5d1c505a47fdacba7546`。同目录201URL静态receipt SHA **`39067e62240159c04206676f8d3b72b90386f27441fc69aa8b45ebf4ff2c00e7`**，新入口index-C0DkAEDU.js SHA `01a7e9ed53b344b935c69d8b6ba9585a6228616902d9a72c34440aafb88829c1`，原CSS和独立资产不变。归档结果待随后追加；不将产物VM测试当真实HTTPS诊断原因。

### 3eee临时adddbb57归档交接与环境释放

标准build与定向全部PASS后，同持续限定root授权仅save同一已测image，不重build。`bash-x1y2f4wt` / Windows PID33556 **112.822秒exit0**；原archiveverifier全blob/index→唯一amd64manifest→config/16有序解压diff_id与归档完整Config对受测inspect等值PASS。原183容器/140卷、daemon/mainlock六guard保持，无新export资源，现无后台，第一Ubuntu明确ENV RELEASED。没有组/socket/defaultuser/daemon配置改动、第二Ubuntu或线上操作，M43 HTTPS/OTA工具未改。

冻结目录：`P:/CRM/.tower/worktrees/wt-37/deploy/.runtime/concentrated-final-adddbb57d809-release/`

| 文件 | bytes / SHA256 |
|---|---|
| `image.tar` | **1557856256 bytes** / `fb5e690c0b89c6557563504fd7c3830dbead4ea6952eaf56fc4205cba0073564` |
| `release.env` | 七字段 / `741e1940f232dcced13c4a524c13ab81252bc835978cb6484311ee2e7aa34b5f` |
| `image-rootfs-layers.txt` | 16有序diff_id / `8e89b5819c8784f807297bdb4ac829600750694fc4ffbef365447e48d833695e` |
| `candidate-manifest.json` | `f58b2c47f3da9303899afb39dd9e94e6ddebac6ef4b28de66accd55414928e16` |
| `export-result.json` | `4f169c68137284170a3c5a525208a93dbeabc844d043727ed6434d2a6cfebecd` |

manifest含精确3eee/3bc/d1c与source receipt5a392a、temporary/显式1及rootcause未知/未部署限制，包与201URLreceipt已直接交tower/M17。此替代旧59b37提前catch采码点，不改变原安全锁页行为，也不是任务修复验收；后续真实采码仍须经过真正lock失败。采证后M24移除临时四源码/开关、保Filter82da/catalog7f305及其余overlay责任不变，off重建仅止采不当移除。M37本轮不部署/浏览器或重复大矩阵。
