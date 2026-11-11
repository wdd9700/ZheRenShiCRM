# 哲人石 CRM

哲人石 CRM 是面向团队的客户资源与商机管理系统，基于 [Frappe CRM](https://github.com/frappe/crm) 扩展，优先把分散的企业资料、联系人、需求与跟进记录连成可查询、可更新、可追溯的数据链条，而不是先做一个 AI 聊天入口。

```text
资源导入 / 录入 → 企业与联系人 → 需求线索 → 商机推进
                                      ↓
                            沟通记录 → 下一步跟进 → 时间线

团队日程：具体时间段安排 → 授权协作 → 忙闲 / 共同空闲
```

**当前 v1 范围是 L0–L3、Windows 使用端与团队集中服务端。** L3.5 的 CRM 与日程业务关联、L4 AI 辅助及其他平台安装包不在本次交付承诺内。功能代码、限定场景验收与完整产品保证是不同概念，具体边界见下文。

## 主要能力

| 层级 | 现有能力 | 使用边界 |
| --- | --- | --- |
| L0 · CRM 基座 | 复用 Frappe CRM 的企业、联系人、线索、商机、任务和活动时间线 | 固定基线为 CRM 1.90.0 / Frappe Framework 15.125.0，不是上游最新版的通用兼容承诺 |
| L1 · 客户资源 | 中文六列 CSV 网页导入，预览、候选消歧、独立确认、重复识别、逐行结果及失败 CSV | 导入限管理权限；企业与联系人涉及共享确认，不是任意 Excel 自动合并，也不是普通成员私域导入 |
| L2 · 跟进闭环 | 需求线索人工转商机，沟通与待办记录、下一步行动、阶段演进；私域活动与显式共享扩展 | 团队身份与服务端权限是基线；“同一团队”不等于所有资料互相可见 |
| L3 · 时间段日程 | 分钟级起止、明确时区、跨日安排、取消、成员读写授权、忙闲与共同空闲、受限 ICS 预览与导入 | 忙闲授权不等于详情授权；冲突仅提示，不自动改排他人；待办截止时间不等于占用时段 |
| 使用体验 | 中文优先、中性暗色、CRM 与日程同源入口 | 少量翻译与措辞未全面覆盖，不承诺全站逐页中文或离线完整可用 |

六列资源表头为：`序号`、`姓名`、`公司名称`、`联系方式`、`公司产品、服务`、`需要的产品、服务`。需求先作为线索保留，**不会因导入自动成为商机**。正式入口和约束见[导入说明](docs/IMPORT_APP.md)；[samples/](samples/README.md) 仅含合成数据，历史 M5 脚本不是生产导入工具。

## 开始使用

### 当前部署实例

以下是当前团队部署实例，**不是无需授权的公共演示站**。账号与权限由管理员提供，首次试用请使用合成资料，不要擅自上传真实客户数据。

- [CRM 工作区](https://8.133.190.46/crm)
- [管理后台](https://8.133.190.46/app)（需要相应权限）
- [团队日程](https://8.133.190.46/team-schedule)
- [私域活动](https://8.133.190.46/team-activities)
- [六列资源导入](https://8.133.190.46/resource-import)（需要管理权限）

建议先由管理员完成合成 CSV 的预览与确认，再在 CRM 查看企业、联系人和需求线索，人工推进商机、记录沟通与下次跟进；日程中单独设置具体起止时间和授权。不要将私密备注默认放入共享企业资料。

### Windows 客户端

目前提供 [Windows x64 1.0.2 安装包](https://8.133.190.46/updates/windows/PhilosopherStoneCRM-Setup-1.0.2-x64.exe)，连接集中服务端，不是自带完整 CRM 服务端的离线安装包。

安装包 SHA-256：

```text
e9c766167e624e59b320e50acd92dff327e0d1c10c42a8f6a08cbaa30e369bca
```

**交付限制：真实 GUI 安装、已安装客户端 N→N+1 覆盖升级及本地数据保留仍待验。** 公开 HTTPS 下载、文件摘要和 Ed25519 OTA 清单验签已有证据，但不能替代安装与自动升级实测。安装器尚无 Authenticode 签名，可能出现“未知发布者”提示；OTA 签名不等于 Windows 发行者签名，也不表示该提示已消除。

Windows 客户端源码尚在[待验分支 `feat/philosopher-windows-exe-persistent-clien`](https://github.com/wdd9700/ZheRenShiCRM/tree/feat/philosopher-windows-exe-persistent-clien)，**未合入主线**。主线没有完整客户端源码目录，不能照主线直接构建此安装包。静态供应与验签记录见[远端执行记录 §21](docs/REMOTE_EXECUTION_C010600.md)。

## 仓库内容与部署入门

**本仓库是扩展、前端补丁和交付工具仓库，不是完整的 Frappe CRM / Framework 上游源码镜像。** 克隆后不能在根目录直接运行一个前端开发服务器，或用通用 `docker compose up` 获得当前全部交付能力。

| 路径 | 内容 |
| --- | --- |
| [apps/resource_import/](apps/resource_import/) | 受认证六列资源导入扩展 |
| [apps/team_access/](apps/team_access/) | 私域活动、团队权限及 CRM 兼容扩展 |
| [apps/team_schedule/](apps/team_schedule/README.md) | 日程模型、权限、忙闲、ICS 与页面实现 |
| [frontend-patches/](frontend-patches/) | 针对固定上游源码的安全、导航、主题、汉化与品牌补丁 |
| [deploy/](deploy/README.md) | 固定版本派生镜像、集成准备、本地实验与远端运维工具 |
| [docs/](docs/) | 使用约束、实施契约、部署记录和验收证据 |

部署者应先准备独立的 Linux Docker 环境、Compose v2、Buildx 与 Python 3；应用运行环境在镜像内。Windows 本地实验记录使用 WSL，**Windows 客户端不替代这些服务端依赖**。构建还需要访问固定上游源码及依赖源；仓库不附带运行凭据、数据库、备份和完整镜像归档。

推荐阅读顺序：

1. [本地实验部署](deploy/README.md)：依赖、固定基线、初始化与安全设置。该文档保留早期实验流程；旧 `manage.py build` 仅为基座兼容路径，不能替代当前安全与界面集成版本。
2. [界面集成与最终交付记录](docs/UI_INTEGRATION_U030.md)：固定源码组合、补丁顺序、资产校验及最终真实 HTTPS 验收。构建需审定源码和匹配制品，不是任意分支拼装。
3. [远端部署工具说明](docs/REMOTE_TRIAL.md)与 [HTTPS 配置](docs/HTTPS_DEPLOYMENT.md)：前者含早期合成试用拓扑，后者说明 HTTPS 与续期机制；**当前线上状态以[远端执行记录 §23–23.1](docs/REMOTE_EXECUTION_C010600.md)为准**，不要把旧 SSH 隧道流程当现行用户入口。
4. [备份与恢复验证](docs/RECOVERY_VALIDATION.md)：数据库、公私文件、配置及应用版本必须一起考虑；先在隔离站点验证，不覆盖现有站点试错。

从仓库根目录可先查看现有本地管理入口，以下命令仅显示帮助，不启动或部署服务：

```sh
python -B deploy/manage.py --help
```

实际初始化、构建、安装与升级请按对应文档逐步执行。已有站点不要重新建站，不要删除卷或卸载应用来“回退”；任何真实资料接入前，先确认认证、权限、备份与恢复安排。

## 开发入门

- 先读[工作协约](docs/AGENT.md)与[决策链](docs/DECISION_LOG.md)，了解固定版本、数据授权和当前范围；产品方向见[渐进式实现交接](docs/商机挖掘系统_渐进式实现交接.md)。历史记录中的“未验”须结合后续追加证据理解。
- 后端扩展按 Frappe app 组织，不能当作独立 Python Web 服务运行。日程安装与现有测试命令见[日程开发说明](apps/team_schedule/README.md)，数据和 API 语义见[L3 契约](docs/SCHEDULING_L3.md)，私域规则见[权限扩展说明](docs/TEAM_ACCESS_EXTENSION.md)。
- 前端是对固定上游源码的补丁，不是完整 Vue 工程；修改前核对目标源码与 before/after 摘要，并按集成文档构建。不要跳过补丁漂移或资产缺失守卫。

例如，日程的纯时间计算测试无需站点，可在仓库根目录的 Bash / WSL 环境运行：

```sh
PYTHONPATH=apps/team_schedule python -B -m unittest team_schedule.tests.test_model_time
```

它只验证时间逻辑，不替代数据库、HTTP、权限或浏览器验收。涉及真实站点的测试只在独立合成环境执行，不使用线上业务库。

## 验收与非目标

已记录的受测范围包括合成导入、普通授权业务流程、隔离备份恢复与服务端升级保数据，以及最终 HTTPS 上的任务列表、筛选中文和日程只读短验。**这些证据不是所有角色、所有页面和所有异常路径的全面安全认证**；详见[最终界面验收](docs/UI_INTEGRATION_U030.md)与[远端交付对账](docs/REMOTE_EXECUTION_C010600.md)。服务端升级保数据证据不能外推为 Windows 客户端升级保数据已验。

- ICS 仅支持约定子集；合成文件导入不代表已接通 Google、Outlook、CalDAV 或双向同步。私人外部账号、对外邀请和通知不因本地功能可用而自动获得授权。
- L3.5 的业务关联与会后结果写回、L4/L5 的 AI 提取和主动助理不在 v1 范围；不提供自动报价、签约或外联承诺。
- 不承诺 macOS、iOS、Android 安装包，也不把响应式页面或 PWA 演进方向说成移动端安装包已交付。
- 不要提交真实客户资料、账号口令、私钥、会话、备份或含秘密的日志。公开仓库样例只使用合成数据。

## 上游与许可证

Frappe CRM 上游声明为 **AGPL-3.0**，Frappe Framework 上游声明为 **MIT**；以各自[CRM 固定源码](https://github.com/frappe/crm/tree/36bd8859f2a6345a620477bc708d0546e8c3f08a)和 [Framework 固定版本](https://github.com/frappe/frappe/tree/v15.125.0)中的许可证与版权声明为准。本 README 不为整个仓库另行授予新许可，各扩展与第三方文件仍需按实际声明核对。提供修改版网络服务时应评估 AGPL 对应源码提供等义务，不能以团队内网使用代替许可证合规判断。
