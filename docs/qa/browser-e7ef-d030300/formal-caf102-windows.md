# 正式服务器 caf102：Windows 最小 UI 验收

## 环境与身份

- Tower/M17 交接正式服务版本为 `caf102`；由 M12 的原启动器提供 `127.0.0.1:18088` 隧道。本记录只证明以下单账号真实后台 UI 场景，不替代服务器升级、权限矩阵或高级恢复验收。
- 内置浏览器在后台操作，`panelVisible=false`；未切换显示面板或抢前台。首次访问带 `redirect-to=/crm` 的新标签时多次得到 `NAVIGATION_FAILED: ERR_CONNECTION_REFUSED`；随后 Windows PowerShell 在 19:55:22 UTC 对 `/login` 返回 HTTP 200。19:57 UTC 新标签直接访问 `/login` 成功进入同端口 CRM，带 redirect 失败的确切原因未查明。
- 直接访问 `/login` 落入已有 Administrator 会话（`text-e47458db-5b69-4fd1-915f-00ee6cee62d6`）。确认当前页无未保存编辑后，依 Tower 明确授权通过 CRM 菜单正常退出该会话；随后使用 M17 新建、仅 Sales User 的合成账号 `v1-ui-acceptance-20261107195038@example.invalid` 正常表单登录。CRM 显示 `V1 UI Synthetic Acceptance` 和空线索列表（`text-a5c54549-1537-487a-81cd-b2f786066560`）。未用 Administrator 做业务操作，未改存储或注入会话。

## 核心结果

- **Lead 创建与刷新回读：通过。** 唯一标记 `SYNTHETIC-FORMAL-CAF102-LEAD-202611072000`，ID `CRM-LEAD-2026-00011`，状态新建，负责人 `V1 UI Synthetic Acceptance`。创建后详情 `text-29649b36-7c69-401b-b5e8-62cbf218313e`；普通整页刷新后同名同 ID 详情 `text-0eaefe32-45f8-4fd5-ba0e-4e19e3df4ec7`。
- **日程创建、编辑、取消：通过。** `SYNTHETIC-FORMAL-CAF102-SCHEDULE-202611072000`，owner 为上述普通账号，UTC 2026-11-20 10:15–10:45，无成员。创建 revision 1：`text-efffbaf5-2ab0-47d4-9461-8bdf673f5cbe`；说明从 `SYNTHETIC-FORMAL-CAF102 initial` 改为 `SYNTHETIC-FORMAL-CAF102 edited` 后 revision 2：`text-f6c8ff4c-e83b-4bc0-984d-9067f83bafb2`；经确认取消（不是删除）后 Busy/Cancelled revision 3：`text-e1da67ca-a2d3-4eb8-934a-f1ad28b01048`。UI 未显示日程 ID。
- **体验观察，未定性：**只改说明、时间不变时，界面提示与本人相同 UTC 时间 Busy 区间交叠（`dialog-f0d4f820-2a8a-414a-8953-36aaba38a7c4`）；接受确认后保存成功。未调查该区间是否是同一条记录。
- **正常注销与后台日程详情清屏：通过本次观察。** CRM 菜单正常注销后转到登录页 `text-f2199bd9-09a2-474f-b830-172cfdca3a59`。未刷新或激活日程标签，后台 DOM `text-4ea56ae8-699f-41c7-aa93-6e5811e5a32c` 显示另一标签账号会话变化、已清除内存业务显示和草稿，先前日程详情消失；静态当前用户名文字仍显示。此次没有预先填写草稿，不能据此宣称草稿清理已验。

## 边界

仅创建上述唯一合成 Lead 与日程，日程已取消但未删除；未修改既有业务记录、角色或权限，未发邮件。未测试真实迟到响应、强制 hidden-visible、双用户授权/撤权、历史全矩阵或高级恢复；本轮不宣称这些能力或完整 v1 通过。先前浏览器控制不可用的 blocker 已解除；之前的连接拒绝及已成功的后续正常路径均按时点保留。
