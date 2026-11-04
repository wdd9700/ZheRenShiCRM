# Team Schedule UI 状态与测试约定

## 状态文案生命周期

- `session-status` 在页面重新可见、BFCache、同源存储变化或请求失败时显示安全边界提示。
- 用户随后主动发起的操作，只有在后端响应成功且通过当前 operation token 检查后，才把顶部提示改为“后续显式请求已成功”的中性状态。旧异步响应不得清除新警告或回填业务数据。
- 取消日程、保存成员或本人占用成功后，清理旧 `schedule-status`，避免上一条编辑 revision 被误当成当前操作结果。
- 保存日程或重新读取详情成功后，清理上一条 `detail-status`。这些清理只针对相关文案，不全局清空表单、业务数据或安全状态。
- epoch、旧请求丢弃、Framework/403 清屏、expected_revision 和请求 DTO 不因文案变化而放宽。

## 本地测试

```bash
node --test apps/team_schedule/team_schedule/tests/ui/team-schedule.test.cjs apps/team_schedule/team_schedule/tests/ui/team-schedule-dom.test.cjs
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider apps/team_schedule/team_schedule/tests/ui
```

`team-schedule-dom.test.cjs` 直接执行生产 `init` 和 DOM 事件，覆盖异步竞争、Framework 错误、长日程、ICS 来源生命周期和状态文案。DOM stub 不是浏览器；真实 Frappe、双账号、实际可见页面和部署后资产仍须在集成窗口单独验收。
