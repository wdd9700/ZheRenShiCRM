# M9 最终 B 候选：R4 团队日程浏览器控制记录

本文件仅记录本人 R4 窗口停点，不代表其后 R5 主控实测；R5 的正常浏览器 UI 观察和矩阵分别见 `R5.md`、`R5-CASES.md`。

**与父目录旧 e7ef 不是同一候选。** M9 交接 image `72d7c4be3c6049b11135d89e544ba6323d061772975ada250a0905cedd328ed3`；M24 产品 `1a1aa0b` + harness `1e01550` / core `5341872` / ICS `4055de2` / UI `cb0745b` / nav `4ff499e` / busy `5eae`。这些是交接信息，不是本轮自行测出的镜像版本。

窗口截止 2026-11-04 14:12:16.600315 UTC；13:54:17 UTC 首次核时尚未截止。入口为 `http://schedule-6a52b79158cb.localhost:8091/login?redirect-to=/team-schedule`。只使用内置浏览器，未启停环境或操作 PDF。

## 已观察与阻碍

本人新建 `panel-tab-484`，正常登录页可达；`browser.switch_tab` 返回 `visible=true`，通过正常表单输入 owner 账号信息时工具一度报告可见。点击登录却报 `TAB_NOT_ACTIVE`；再 `browser.activate_tab` 报 `BROWSER_UNAVAILABLE: Browser control requires a running turn`。浏览器状态一度 `visibleTabId=panel-tab-484` 但 `activeTabId=null`，后续截图显示普通登录表单且当时 `visible=false`。截图 `login-tool-blocked.png` 为工具阻断时实际页面，密码为掩码；该截图不证明登录成功。主控正排查浏览器控制绑定；没有调用 API 或注入会话代替。

主控检查后重新 `activate_tab` 成功，但 `visible=false`；本人随后一次 `switch_tab` 返回 `BROWSER_UNAVAILABLE: This session is not being viewed`。主控报告其会话也无法显示该标签，不能确定只需切至子会话即可恢复；未反复重试，未在隐藏状态提交。登录未提交、无业务对象创建，不把该工具异常当成产品认证失败。收尾时再次 `activate_tab` 报 `Browser control requires a running turn`，因此未能单独清空表单；`browser.close_tab` 成功关闭本人标签，其他原有标签未碰；没有已登录账号需要注销。已通知 M9 结束本轮，不自行 release 或停环境。

CRM 导航、日程创建/编辑/回读、owner/peer 权限和撤权、跨标签恢复、忙闲、ICS 更新取消以及脚本字面安全均尚未执行。M9 的构建、静态及 HTTP 门结果不代替 UI 验收。PDF 500 为独立已知失败，本轮未操作 PDF，不声称整体安全通过。
