# 哲人石CRM U030 标准组合与登录品牌

状态：实现与离线核验中；尚未完成审定输入的 Linux 标准组合构建、最终镜像回归或 Terra 核心界面烟测。没有更改线上服务、数据库或部署锁。

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
