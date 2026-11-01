# 试用站点 Administrator 密码变更记录（C010700）

**状态：已完成——变更已写入并用真实登录接口核验身份。** 用户在明确授权"允许跳过强度检查"后，同意把合成试用站 `crm.localhost`（`dev@8.133.190.46`，project `crm-trial-c010400`）的 `Administrator` 口令设为本轮指定的 6 位值（含前导 0），账号不变。全站密码策略、`.env`、数据库秘密、SSH 与端口均未改动。本文件不含口令、cookie、session 或 `.env` 内容。

## 1. 范围

| 已执行 | 未执行 |
|---|---|
| 严格 SSH 下用官方 `bench set-admin-password`，口令仅经 stdin | 改 `enable_password_policy` / `minimum_password_score` |
| 一次真实 HTTP 登录 + `get_logged_user` 身份核验，事后注销该验证会话 | 改 SSH 口令、DB 口令、`.env`、防火墙/安全区、端口暴露 |
| 只读复核策略与账号状态 | 直接 SQL 改 hash、重 `init`、停服务、删除或重建资源 |

## 2. 连接与版本

Git Bash `ssh`，`-o UserKnownHostsFile=…/m10-known_hosts -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o BatchMode=yes`；私钥只作 `-i` 参数，未读取/打印/复制。指纹与 M10/M14/M15 一致：

```
256 SHA256:JHFV75F2oc1tYqjd4viv130aknkd7fOwtKEpmGtgy80 8.133.190.46 (ED25519)
```

`crm 1.90.0` / `frappe 15.125.0` / `resource_import 0.1.0` / `team_access 0.1.0`；9 个长驻服务 Up（db healthy）。容器内以 `frappe` 用户执行，`sudo -n docker` 可用。

## 3. 授权例外（关键约束）

| 项 | 值（只读复核，前后一致） |
|---|---|
| `enable_password_policy` | 1（启用，**未改**） |
| `minimum_password_score` | 2（**未改**） |

站点自身策略接口（`POST /api/method/frappe.core.doctype.user.user.test_password_strength`）对本次口令返回 `score=1`、`password_policy_validation_passed=false`，而受支持的 `bench set-admin-password` 走 `frappe.utils.password.update_password()`，只写 passlib 哈希到 `__Auth`、不跑策略校验。

因此本次写入属于用户**明确授权的一次性例外**："允许跳过强度检查"，仅限本次 Administrator 重置。它**不是**放宽全站策略，也**不构成**今后设置任意弱口令的许可；后续任何改密仍应按 `enable_password_policy=1` / `minimum_password_score=2` 执行。

## 4. 执行

```
bench --site crm.localhost set-admin-password        # stdin 提供口令，exit 0
```

- 口令通过 `printf … | docker compose exec -T backend bench …` 的 **stdin** 送入；`-T` 下无 TTY，getpass 从 stdin 读取，终端只出现 `Password input may be echoed` 警告（无回显内容）。
- 口令未写入 argv、脚本文件、临时文件、日志、Git 或本记录。
- 未重启服务，未改 `.env`、DB 秘密、站点配置、SSH、防火墙或端口；未重 `init`。

## 5. 真实登录核验（API 级，非浏览器验收）

经 `http://127.0.0.1:8088`（`Host: crm.localhost`）单次会话，cookie 只在内存 `CookieJar`，未打印、未落盘：

| 步骤 | 结果 |
|---|---|
| `POST /api/method/login`（`usr=Administrator` + 新口令） | HTTP 200，`message = "Logged In"`（成功） |
| `GET /api/method/frappe.auth.get_logged_user` | `message = Administrator`，身份匹配 |
| `POST /api/method/logout` | HTTP 200，会话注销 |
| 注销后 `tabSessions` 中 Administrator 行数 | 0（验证会话已消失，无遗留、未误杀其他会话） |

账号状态（只读）：`Administrator` `enabled=1`、`System User`、`last_password_reset_date=2026-11-01`（由 bench 写入）、`__Auth` 行存在（`fieldname=password`、`encrypted=0`、哈希长度 87，未读取哈希内容）。

`logout_on_password_reset=1` 属原配置；本次 CLI 路径不主动清理其他会话（执行前后该账号本无其他会话）。若用户浏览器里还留有改动前登录的旧标签页，其会话属原生行为，需要时自行登出即可。

## 6. 凭据权威

- `deploy/remote/.runtime/.env` 中的 `ADMIN_PASSWORD` 是 `init-env`/建站时的**随机初始化值**，已被本次重置覆盖、**不再有效**，不建议再读取它尝试登录。本合同未读取、未打印、未复制、未回传该文件，也未为"保持一致"去同步它（避免触碰 DB 秘密）。
- 当前权威：用户本轮指定、并已按上述方式写入站点的口令（由用户自己掌握，不记录在任何文件或提交中）。

## 7. 未验收项

- **真实浏览器表单登录未验收**：只有 API 级身份核验，不得把上面的 HTTP 结果当作浏览器验收；登录页资产/MIME、表单交互仍待人工确认。
- Windows 隧道 / `127.0.0.1:18088` 接入、Edge PWA、权限矩阵、登录限流实测均未做（未主动制造失败登录）。
- 本次是单次口令重置，未评估该弱口令在公网暴露或长期使用下的风险；站点仍仅监听回环。
