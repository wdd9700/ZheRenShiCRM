# Framework 引导组件翻译与中性按钮补丁

适用 Framework 15.125 固定来源，三个文件原始/结果 SHA256 见 `manifest.json`；任何一字节不同一律拒绝，不能套用于其他版本或已经单独修改的同一文件。保留原上游著作权和许可证。此补丁不改变内部 `appName`、步骤名称、动作、回调参数、权限和用户数据，不扫描或改写 DOM。

CRM 原生补丁 `../localization` 提供词典与翻译插件。三个组件用 Vue 当前应用上下文的 `appContext.config.globalProperties.__`，即 CRM 安装的翻译器，而非假设模块作用域中存在 `__`；未安装时按英文原文及占位符回退。欢迎语使用完整 `Welcome to {0}` 模板和翻译后的展示标题，中文默认标题为哲人石CRM，其他语言遵循原生服务端词典；内部 `frappecrm` 不变。语言判断和服务端翻译优先规则见相邻目录。

## 构建顺序及冲突

先完成上游依赖安装与既有必要源码补丁，然后应用 CRM `localization` 和本 Framework 补丁，再构建 CRM 资产。`FRAMEWORK_ROOT` 是包含 `ui/` 的实际 Framework 源码根，并非 CRM 根，也不是 `frappe-ui` npm 包。三个目标须列入 Framework 根源码变更白名单，和 CRM 根白名单分开。集成构建须显式复制本目录 `apply.py`、`manifest.json` 及相邻 localization 目录，并在资产构建前执行：

```sh
python frontend-patches/localization/apply.py "$CRM_ROOT" --check
python frontend-patches/localization/apply.py "$CRM_ROOT"
python frontend-patches/localization/apply.py "$CRM_ROOT" --verify
python frontend-patches/onboarding-localization/apply.py "$FRAMEWORK_ROOT" --check
python frontend-patches/onboarding-localization/apply.py "$FRAMEWORK_ROOT"
python frontend-patches/onboarding-localization/apply.py "$FRAMEWORK_ROOT" --verify
```

Sol 样式建议已与文本**在同一输出中合成**：`GettingStartedBanner.vue` 的 `theme="blue"` 改为 `theme="gray" variant="subtle"`；不要在此文件再运行单独样式补丁。其他补丁如涉及三个目标，必须对固定来源重新组合、更新前后 SHA 并重审，不可跳过 hash。所有输入和临时路径先验证，再暂存、替换；失败尝试回滚，回滚失败保留原始备份并报错，不承诺掉电事务。LF 与字节哈希必须匹配。

## 测试

```sh
FRAMEWORK_BASELINE=/path/to/frappe \
CRM_TRANSLATION_BASELINE=/path/to/crm/frontend/src/translation.js \
CRM_FRONTEND_NODE_MODULES=/path/to/crm/frontend/node_modules \
python frontend-patches/onboarding-localization/test_onboarding.py
```

测试临时复制固定源（不修改源目录），验证哈希/冲突拒绝及注入替换故障的回滚、check/apply/verify；使用固定前端依赖的 Vue SFC 编译器编译三个补丁后模板与脚本；用真实 CRM 翻译插件执行中英文及服务端法语例子、欢迎语和进度表达式，静态核对引导按钮/回调参数。另运行相邻 `localization/test_localization.py` 验证上下文、语言与占位符。测试不等于完整资产构建、浏览器交互或真实站点语言设置验收；由 M37 构建集成和 Sol 独立审查，禁止本任务部署。
