# 哲人石CRM原生翻译补丁

适用上游 Frappe CRM 固定提交 `36bd8859f2a6345a620477bc708d0546e8c3f08a`。保留上游著作权及其许可证；展示名不改变上游法律归属。补丁不改 DocType、API、业务状态或用户记录，也不扫描 DOM。

## 构建集成

先完成上游依赖安装及 C011000 cache 补丁，再应用本补丁（与 dark-ui 不重叠；应分别验证各自补丁），然后运行正常 `bench build --app crm`。`CRM_ROOT` 指固定提交的 CRM 源码目录，三个命令分别为预检、应用、最终校验：

```sh
python frontend-patches/localization/apply.py "$CRM_ROOT" --check
python frontend-patches/localization/apply.py "$CRM_ROOT"
python frontend-patches/localization/apply.py "$CRM_ROOT" --verify
```

所有输入先核对 HEAD、每个来源字节 SHA256 和新增文件不存在，再写入。哈希按上游 Git blob 原始 LF 字节计算，Windows `core.autocrlf=true` 的 CRLF 检出会被拒绝；请在干净检出中保留原始 LF，不要跳过校验。已应用或其他补丁修改了同一文件时，预检会拒绝；应重新基于固定源码组合及重审。`--verify` 校验应用后的全部内容。版本、输入及输出的 SHA256 以 `manifest.json` 为准；这里只改 `crm/www/crm.py`、`frontend/src/translation.js`，新增 `frontend/src/philosopher-zh-cn.json`。若部署有源文件变更白名单或最终产物完整性校验，必须显式加入这三个目标，以及本目录 `apply.py`、`manifest.json`、`zh-CN.json`；测试源码 `test_localization.py`、`runtime.test.cjs` 不需进镜像。该目录不会自动进入构建上下文或镜像，集成者必须显式 COPY 和运行。

`apps/team_schedule/team_schedule/public/crm-zh-cn.js` 是独立静态纯文案；要纳入 team_schedule 的资源复制及新资产白名单，并由页面在 `team-schedule.js` 之前以 defer 加载。接口 `window.PhilosopherCRMText` 和其 `enums`、`timeline`、`icsActions`、`errors`、`dates` 子映射均冻结。调用方只翻译呈现，未知键回退原始值，必须保留 option.value、请求、状态和时间值，不将字典或用户数据插入 HTML 字符串；使用 textContent。时区仍由原逻辑选择并显示 IANA 时区及 UTC 偏移，不因为语言修改。

## 语言和限制

`get_boot` 增加 `philosopher_language`，取本次 Frappe 请求实际 `frappe.local.lang`；`translation.js` 仍使用原生 `getConfig('translatedMessages')`、context 优先与 `{0}` 格式化。仅当语言为 `zh`、`zh-CN`、`zh-Hans` 或 `zh-Hans-*`（大小写及下划线变体均可）查找简体中文补充词典，同键服务端翻译优先；其他语言仅走上游原行为。服务器不设语言时不猜测。中文默认须由集成者通过 Frappe 原生站点默认语言配置实现，不批量更改用户明确设置；Frappe 用户语言、请求语言选择行为保持原生。正式部署需验证目标站点具体语言值和会话刷新。

此补丁只覆盖 CRM Vue 已经调用 `__` 且词典有记录的文本，不会覆盖未调用 `__` 的硬编码、动态用户内容、Frappe UI 内部独立翻译、服务端返回的未知文本或 Framework `/login`。登录/Guest、本地扩展静态页面、动态相对时间和余下文案由后续单独接入；不要将本词典描述为全站汉化。`Frappe CRM` / `CRM` 的可翻译展示名为“哲人石CRM”，PWA、页面标题等非翻译路径需由集成者单独处理。

## 检验

针对固定版本的两个原始文件运行，路径示例仅用于本机证据来源：

```sh
CRM_PY_BASELINE=/path/to/crm/www/crm.py \
CRM_TRANSLATION_BASELINE=/path/to/frontend/src/translation.js \
python frontend-patches/localization/test_localization.py
```

测试复制两个来源至临时目录，模拟固定 HEAD（不声称验证了真实 Git HEAD），执行 check/apply/verify、来源哈希拒绝、服务端 get_boot、占位符、context、语言选择、服务端词条优先级及冻结字典契约。实际 Git checkout 的 HEAD 检验、完整上游构建、登录和浏览器联调由集成验收完成。
