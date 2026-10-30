# tools/xerj — 本项目可选的本地检索后端

XERJ 是**可选**的本地检索工具，用于减少主 Agent 在文档/代码中反复搜索的上下文开销。它不是 CRM 的前置条件；节点未运行、索引未建立或检索效果不佳时，继续使用 Grep / Glob / Read 即可。

本目录只包含最小的启动、停止、索引与查询封装，不包含 XERJ 本体，不安装软件，不启用 MCP，不提交自动反馈，不下载模型。

## 固定配置

| 项 | 值 |
|---|---|
| 索引根 | `P:\CRM`（仅主工作区，不含任何 worktree） |
| prefix | `crm-main` |
| API / 端口 | `http://127.0.0.1:9200`，同时占用 9201/9202；仅 loopback |
| 嵌入模式 | `lexical`（内置离线 feature-hash，不是神经语义模型） |
| 索引模式 | `--no-semantic --no-graph --code-analyzer code` |
| 运行时目录 | `P:\CRM\.tower\xerj`（隐藏目录；autoindex 与 git 均排除） |
| 数据 | `.tower\xerj\data`（含 `admin.key`） |
| 索引日志/状态 | `.tower\xerj\state\crm-main`（autoindex 断点 journal） |
| 进程状态 | `.tower\xerj\run\node-state.json` |
| 节点日志 | `.tower\xerj\logs\node-*.out.log` / `*.err.log` |

`.tower` 是点目录：autoindex 默认无条件跳过隐藏路径，因此节点数据、日志、索引 journal 不会被自己收录；`.tower/` 也已列入 `.git/info/exclude`，不会出现在 `git status`。

## 脚本

所有脚本使用已安装的绝对路径 `%LOCALAPPDATA%\Programs\xerj\xerj.exe`（可用 `XERJ_CRM_EXE` 覆盖）。在 PowerShell 中：

```powershell
# 启动（后台，等待 9200 就绪后返回）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-start.ps1

# 前台启动（便于看日志，Ctrl+C 停止）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-start.ps1 -Foreground

# 状态（-Map 额外打印已索引数据地图）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-status.ps1

# 停止（只停止自己记录的 pid；保留数据和索引）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-stop.ps1

# 索引：默认 dry-run，不写索引
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-index.ps1

# 索引：确认范围后正式写入
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-index.ps1 -Apply

# 增量：同一命令再跑一次 -Apply；只处理变更文件
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-index.ps1 -Apply

# 查询：默认 3 段、每段最多 500 字符
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-search.ps1 -Query "具体模块 + 标识符 + 行为" -K 3 -Full 500

# 已知符号（语料含代码后才有意义）
powershell.exe -NoProfile -ExecutionPolicy Bypass -File P:\CRM\tools\xerj\xerj-search.ps1 -Def -Query "ExactSymbol" -Lang typescript
```

从 Bash / Git Bash 调用时路径用正斜杠：

```bash
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "P:/CRM/tools/xerj/xerj-index.ps1" -Apply
```

`xerj-env.ps1` 是共享配置，被其他脚本 dot-source。修改索引根、prefix 或端口需要改这个文件；日常不要改。

## 索引参数与退出码

正式索引等价于：

```text
xerj autoindex P:\CRM --prefix crm-main --state-dir P:\CRM\.tower\xerj\state\crm-main
  --code-analyzer code --no-semantic --no-graph --workers 4
  --max-file-mb 10 --max-index-size 2GB --max-minutes 10 --progress plain
```

脚本**不会**自动附加 `--yes`、`--drop-indexed` 或 `--replace-prefix`。这些会代表用户接受缩减计划或删除已索引文档，必须由人明确决定。

- `0`：语料可检索。
- `3`：完成但存在跳过/拒绝的文件，需看原因。
- `4`：需要决策（预算/范围），脚本原样返回，不自动继续。
- 其他：检查节点日志与 journal。

第一次索引前先跑默认 dry-run，检查文件数、隐藏目录排除项、估算大小与磁盘预算。变更文件后重复 `-Apply` 即为增量协调；只有 journal 损坏或需要重规划时才用 `-Fresh`。

## 路径迁移

节点数据与索引状态可整体迁移，脚本不会删除任何目录：

1. `xerj-stop.ps1` 停止节点。
2. 选定新的绝对目录，例如 `D:\xerj-crm-home`。
3. 复制 `P:\CRM\.tower\xerj` 下的 `data\`、`state\`、`logs\` 到新目录，保持同名结构；`run\node-state.json` 可不复制（下次启动会重建）。
4. 在启动脚本所在会话设置 `XERJ_CRM_HOME=D:\xerj-crm-home`（需要永久生效时再写入用户环境变量）。启动脚本优先使用该变量。
5. `xerj-start.ps1` → `xerj-status.ps1 -Map` → 两条已知查询验证；确认后再人工处理旧目录，脚本不会代删。

注意：`admin.key` 随 `data\` 迁移，客户端脚本会自动从新的 `data\admin.key` 读取，不要把 key 写进命令行、文档或日志。若要换索引根或 prefix，改 `xerj-env.ps1` 并重新索引；不同 prefix 不要复用。

## 安全与当前实验边界

- 仅绑定 `127.0.0.1`，不使用 `--insecure`，不绑定 `0.0.0.0`，不开放公网。
- 仅索引 `P:\CRM`；`.git`、`.tower`（含所有 worktree）由隐藏规则排除。脚本按固定根启动，不会误扫其他盘或目录。
- 保持默认 API-key 认证；不要打印、提交或外传 `admin.key`。节点首次启动的 stderr 可能包含一次性 console setup 链接，日志同样不要外传。
- 当前语料只有项目文档，没有客户数据。这是 **loopback 实验模式**；一旦引入真实客户资料，必须重新评估认证、加密、保留期与访问边界，不能把当前实验当生产安全方案。
- 不启用 neural/proxy 嵌入、不下载模型、不启用 MCP、不提交 feedback。

## 已验证 / 未验证（2026-10-31 实测）

已验证：

- dry-run：`P:\CRM` 共 4 个文件、36.8 KB；`.git` 与 `.tower` 作为隐藏目录被剪除，未进入扫描。
- 正式索引：exit 0，1 个数据集、27 条记录、generation 1。
- 两条已知答案查询均 top-1 命中：`AGENTS.md:31`（Workspace Activation）与 `docs/DECISION_LOG.md:10`（决策状态定义），并与当前原文核对一致。
- 增量空跑：0.5 s，仍为 generation 1 / 27 条，无重复。
- 重启持久化：停止后重新启动，同一查询仍 top-1 命中。
- 停止后 9200/9201/9202 全部释放；监听地址均为 `127.0.0.1`。
- 未打印 `admin.key`。

未验证：

- 新增/修改/删除文件的增量协调（本轮没有改动被索引的源文件）。
- `def` 与代码符号检索（当前语料只有 Markdown，无代码）。
- 路径迁移流程本身（只给出步骤，未实际搬迁）。
- 更大语料、检索质量与延迟、并发查询。
- MCP、console UI、开机自启/Windows 服务。
- 神经语义能力（未启用，且 lexical 明确不是神经模型）。

检索结果是证据候选，不是结论。命中后应 Read 当前源文件核验；具体查询一次改写仍无结果时，回退 Grep/Glob，不反复重试。
