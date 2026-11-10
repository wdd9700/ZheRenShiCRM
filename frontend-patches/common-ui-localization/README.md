# CRM 常用界面翻译接线补丁

仅适用于 CRM 固定提交 `36bd8859f2a6345a620477bc708d0546e8c3f08a`，配合相邻 `localization` 字典使用；集成者须显式将此目录加入构建上下文，在正常资产构建之前执行：

```sh
python frontend-patches/localization/apply.py "$CRM_ROOT" --check
python frontend-patches/localization/apply.py "$CRM_ROOT"
python frontend-patches/localization/apply.py "$CRM_ROOT" --verify
python frontend-patches/common-ui-localization/apply.py "$CRM_ROOT" --check
python frontend-patches/common-ui-localization/apply.py "$CRM_ROOT"
python frontend-patches/common-ui-localization/apply.py "$CRM_ROOT" --verify
```

此补丁只把通知面板空态的标题和说明、详情保存按钮、筛选复选项的显示标签及表情搜索的静态文案接入原生 `__`；移动通知原来已调用 `__`。共用空态组件将显式 title/description 原样输出，因此仅增加字典键不足以修复桌面通知。筛选字段仅对固定 CRM Lead/CRM Deal 系统字段中字段名和英文标签均匹配的条目调用翻译；自定义字段、被自定义的标签、服务端已翻译的标签及其他 DocType 均原样显示，字段名和值不改。表情分类、用户内容和通知正文不改。字典另覆盖已调用 `__` 的常用搜索、空态、筛选、创建编辑与菜单文案；服务端同键翻译优先，其他语言回退上游行为，不能称为全站汉化。

所有输入先校验 HEAD、目标 SHA256、唯一锚点和输出 SHA256（见 `manifest.json`），再暂存文件及备份并替换；异常时回滚，回滚失败保留备份。这不是掉电级事务；CRLF、改动过的源文件或临时路径冲突会拒绝，不应绕过检查。部署需将四个 manifest 目标纳入源码/产物白名单，且与其他补丁分别验证。

必要本地检查（基准指向固定版本公开源码）：

```sh
CRM_SOURCE_BASELINE=/path/to/crm python frontend-patches/common-ui-localization/test_common_ui.py
```

此检查使用复制的源文件和模拟 HEAD，不代替固定源码真实构建或目标环境实际页面确认。发布后应实际检查桌面及移动通知空态、筛选和搜索等相关控件；不应把测试通过等同于汉化验收。
