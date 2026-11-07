# 观测证据索引

日期 2026-11-04，均为本轮 Kimi Code Desktop 内置浏览器真实页面。`snapshotId` 是本会话转录引用，非可跨会话重放的永久链接。后台截图是浏览器捕获，不表示当时用户能见到页面。未记录口令、cookie 或令牌。

1. Guest 登录：`panel-tab-40` 首次显示；`text-7a39c93d-7fd0-4043-89a0-d19cc0f0ac17`，截图 `01-guest-login.png`。此后会话非用户视图时切换面板曾失败；08:12激活面板成功且截图 `visual-18c7cce5-5497-4168-92a8-adcf3591e642` 的tab `visible=true`。后续输入时为 `visible=false`。
2. A 表单：正常输入并点击登录，`text-8092170b-8a3b-4ecf-a236-4b3d8c95695f` 显示身份确认；20秒等待超时后，`text-2091e534-c498-4150-ada9-8aa7d0be32a2` 显示 A 和空Lead列表。不能以等待超时推断服务器根因。
3. A Lead：创建弹窗填写 `D030300-A-Lead`，截图 `02-a-lead-create.png`；正常点击 Create，`text-e2713234-94ff-462a-94f4-fb569e6e8005` 显示名称、负责人和 `CRM-LEAD-2026-00005`，截图 `03-a-lead-detail.png`。reload后30秒仍身份确认；后续 `text-ec4f2bff-0d2b-4302-8322-a9d124445bfe` 已为详情。此标签恢复详情的精确时点未知。
4. A Note：本人 `panel-tab-101` 正常活动页控件输入标题 `D030300-A-Private-Note`、正文 `D030300 synthetic private note associated with A lead.`、父 `CRM Lead` / `CRM-LEAD-2026-00005`、Private、无协作者；`elements-f8858f8d-7466-4bff-8a73-d239b383916d` 为提交前值，保存后 `text-b561d1f3-c55d-4722-b5a9-3626e01c8427` 为成功及列表项。点刷新再点条目，`elements-abf21d08-2010-4ab0-8546-817e6d01b77a` 回显正文和父关联。
5. A Task：相同页面切换 CRM Task，标题 `D030300-A-Private-Task`、正文 `D030300 synthetic follow-up task for A lead.`、相同父Lead、Private、无协作者或受派人；提交前 `elements-9118d83d-fd64-45a5-a825-0fcf174007ab`，保存结果 `text-ab006dd7-e3ca-4cfb-9af8-a36605b6b524`。点刷新再点条目，`elements-105c7bf3-be2d-4c53-bba5-137891dfafa4` 回显正文和父关联。两个活动系统ID未显示。
6. A正常退出：活动页菜单 Log out 后 `text-d3470d6a-989f-40a9-ad77-fd7587914f49` 显示成功。另一个未刷新旧标签 `text-ec4f2bff-0d2b-4302-8322-a9d124445bfe` 仍显示A、该Lead名称和ID。不是匿名服务端读成功的证据。
7. B正常表单提交；`/crm/` 等待30秒仍身份确认，然后正常导航活动页，`elements-3f212581-9a34-4653-993a-1c9382c0d5e8` 显示B身份、Note活动0；切换 Task 后 `elements-fc939802-ddff-4fbf-98fd-0c651183a644` 活动0。B直接打开A Lead详情等候30秒仍身份确认，既未观察明确拒绝也未观察详情。`text-f5032743-855b-4dab-be4e-aa0507aea869` 显示未刷新旧A标签仍为A与Lead，不代表B可向服务器读该Lead。
8. B活动页账户菜单正常注销后 `text-8a7cda56-ef0c-45d8-8f48-c2ed2a4b1423` 显示成功。仅本人 `panel-tab-101` 和 `panel-tab-40` 已关闭；原本存在的四个故障标签未碰。活动页后台截图曾 `PAGE_NOT_READY`，故以文本/元素快照记录，不把工具阻碍当产品缺陷。
