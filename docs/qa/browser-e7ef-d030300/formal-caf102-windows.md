# 正式服务器 caf102：Windows 最小 UI 验收

## 当前结果

- 2026-11-07 UTC，内置浏览器 `browser.get_state` 可用，`panelVisible=false`；未显示侧栏或接管前台。
- 依据 M12 隧道 READY 和 M17 新普通合成账号交接，在后台通过 `browser.create_tab` 访问 `http://127.0.0.1:18088/login?redirect-to=/crm`，实际返回 `NAVIGATION_FAILED: ERR_CONNECTION_REFUSED`。因此未进入登录页、未登录、未创建或修改任何业务记录。
- M12 重新确认系统级独立宿主持久隧道后，约 19:54 UTC 再做一次后台原生 `browser.create_tab` 导航，同样返回 `NAVIGATION_FAILED: ERR_CONNECTION_REFUSED`。随后 19:55:22 UTC，Windows PowerShell 对相同主机端口的 `/login` 发起 `Invoke-WebRequest` 返回 HTTP 200；内置浏览器与 Windows 客户端的可达性不同，原因未证实。此 HTTP 检查不是 UI 验收。
- 已通知 Tower 和 Windows 原启动器负责人核查；未自建转发。凭据未写入本报告。

## 未验

正式服务器的普通账号正常登录、合成 Lead 创建与刷新、日程创建/编辑/取消和正常注销均未执行；跨标签退出、高级恢复及双账号权限矩阵亦未测试。远端升级、schema 和 HTTP/socket 的既有独立证据不替代本次 Windows 真实 UI 验收。
