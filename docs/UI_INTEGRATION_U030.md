# 哲人石CRM U030 标准组合与登录品牌

状态：首轮 d573 标准构建/native326/bridge/SFC 已过并完成一次真实 UI 窗口，反馈的视觉/引导缺口已集中修复。第二批 v3 候选 6d143 已完成一次标准构建及实际产物改动定向检查；等待同一 M32 站定点视觉复验，未宣全部视觉通过。M37没有更改线上服务、数据库或部署锁。最新身份与 receipt 见文末，首轮历史保留。

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
