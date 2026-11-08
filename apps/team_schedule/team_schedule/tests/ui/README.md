# Team Schedule UI 状态与测试约定

## 状态文案生命周期

- `session-status` 在页面重新可见、BFCache、同源存储变化或请求失败时显示安全边界提示。
- CRM 现有 `crm-account-boundary-c011000` BroadcastChannel 的字符串 `changed` 也调用同一失效处理。仅接收该约定消息；API 不存在或构造失败时保留原有兜底，不写业务存储、不轮询。
- 用户随后主动发起的操作，只有在后端响应成功且通过当前 operation token 检查后，才把顶部提示改为“后续显式请求已成功”的中性状态。旧异步响应不得清除新警告或回填业务数据。
- 取消日程、保存成员或本人占用成功后，清理旧 `schedule-status`，避免上一条编辑 revision 被误当成当前操作结果。
- 保存日程或重新读取详情成功后，清理上一条 `detail-status`。这些清理只针对相关文案，不全局清空表单、业务数据或安全状态。
- epoch、旧请求丢弃、Framework/403 清屏、expected_revision 和请求 DTO 不因文案变化而放宽。

## 本地测试

```bash
node --test apps/team_schedule/team_schedule/tests/ui/team-schedule.test.cjs apps/team_schedule/team_schedule/tests/ui/team-schedule-dom.test.cjs
PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider apps/team_schedule/team_schedule/tests/ui
```

`team-schedule-dom.test.cjs` 直接执行生产 `init` 和 DOM 事件，覆盖异步竞争、Framework 错误、长日程、ICS 来源生命周期、BroadcastChannel 失效和状态文案。M35增加真实分钟/短块、重叠分列、跨日裁切、DST 23/25小时、重复小时offset、两次当地午夜解析、分页完整性提示、日期导航竞争和409清除时间轴覆盖。DOM stub 不是浏览器或真实后端。

## 时间轴与字典契约（M35）

- 默认日视图需显式加载，日期和IANA时区始终可见；日边界通过现有`resolve_local`分别解析当地午夜和下一日期午夜，不用固定24小时推导。罕见午夜歧义或不存在时拒绝自动选择，转自定义窗口明确DST offset。
- 连续轴为每真实UTC分钟1.2px；半开区间裁切，跨日标承接/延续；同一重叠簇贪心分列，相邻端点不重叠。短事件不设虚假最短占用时长；下方编号列表保留完整可访问标签，点击仍由`get`重新核权。
- 日程的Busy/Free不是对方已接受占用的推论；脱敏忙闲继续使用独立query，未把详情数据转成忙闲数据。
- 全部新时间轴节点、title、标签和闭包随`schedule-list.replaceChildren()`清除；`listGeneration`阻止旧日期响应回填，epoch/会话边界继续优先。
- `crm-zh-cn.js`由M36独占，defer先于页面脚本；只读`window.PhilosopherCRMText.enums`/`.timeline`/`.errors`/`.icsActions`，未知值安全回退。请求、option.value、DocType和成员权限值保持原始值。
- `crm-theme.css`是canonical，CRM payload必须逐字相同。独立补丁验证：`PYTHONDONTWRITEBYTECODE=1 python frontend-patches/dark-ui/check_apply.py`。M24生产43entry→M30导航→dark-ui→localization；dark-ui的`--verify-after`在localization前执行，最终App.vue after归最后覆盖补丁。

本轮未部署或运行真实浏览器/站点测试；标准CRM构建及三页实际样式、移动端/高并发横滚与跨标签logout实测留给集成独审后的窗口。Framework登录、CRM入口HTML/PWA品牌和后续串行汉化不在这4target独立补丁中。
