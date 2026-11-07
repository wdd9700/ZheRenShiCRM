# 最终 B 候选 R5 用例矩阵

本矩阵 R5 业务观察来自主控正常内置浏览器 UI 操作及其工具快照，非本人绕过控制失败后重做；后台操作属于真实 UI。PASS 仅涵盖行内限定断言，NOT RUN 不计通过。

| 场景 | 状态 | 主控工具证据及边界 |
|---|---|---|
| owner 正常表单登录至团队日程 | PASS | 正常元素点击表单，进入 `/team-schedule`；未使用API或注入会话。 |
| 团队日程→CRM→侧栏团队日程 | PASS | 正常点击返回及侧栏入口；主控 DOM `text-b32b84c7` 看到 CRM/Leads/团队日程入口。 |
| 新建日程 | PASS | `SYNTHETIC-UI-R5-1422 <b>literal</b>`、UTC 11月5日09–10、Busy、无成员；`text-e9afdedf-252a-46c7-8f6d-69e25f1a8055` 显示创建、revision 1、标题说明。`r5-schedule-input.png` 仅为创建前输入过程，不是创建结果截图。 |
| 编辑日程 | PASS | 修改说明并保存，接受自身Busy交叠的原生确认；`text-6b3b4773-06d1-48a7-b04a-f3f46c858c44` 显示 revision 2 和新说明。自身冲突提示是否缺陷尚未定论。 |
| 记录系统 ID 与持久化旁证 | PASS（M9数据库只读核证，非 UI） | 主控 UI 写后 M9 按唯一标题和 owner 核得 ID `4d77e90b1b11f3c2c93d47932f207485`、creation `2026-11-04T14:40:44.315880Z`、revision 2、Active/Busy、UTC 11月5日09:00–10:00及标题和编辑正文原文一致；页面未显示 ID，不能以只读结果代替 UI。 |
| owner 注销与本人标签关闭 | PASS | 返回 CRM 后正常菜单 Log out，`text-81e18965-93aa-43a3-bea7-e6ed163bc96b` 显示登录表单；关闭本人547。截图 `r5-crm-logout-menu.png` 是注销前菜单，不是注销结果。 |
| peer 登录、私有隔离、共享协作及撤权 | NOT RUN | 未执行。 |
| M24 旧标签隐藏返回、可见恢复或注销后清屏 | NOT RUN | 未执行，不注入 visibility。 |
| 8天 Free / 31天 Busy | NOT RUN | 不以单次一小时 Busy 创建代替。 |
| ICS 来源导入、刷新更新及取消 | NOT RUN | 未操作。 |
| script/img 与无外联 | NOT RUN | `<b>` 字面显示不证明脚本或外联安全。 |
| L2 Lead / Note / Task、商机 | NOT RUN | 本轮日程结果不代替旧业务闭环。 |
| PDF | NOT RUN | PDF 500 为独立已知失败；遵照指示不操作。 |
