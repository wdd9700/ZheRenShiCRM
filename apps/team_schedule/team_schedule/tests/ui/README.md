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
- 连续轴为每真实UTC分钟1.2px；半开区间裁切，跨日标承接/延续；同一重叠簇贪心分列，相邻端点不重叠。短事件不设虚假最短占用时长；同轴旁侧编号列表保留完整可访问标签，点击仍由`get`重新核权。
- 日程的Busy/Free不是对方已接受占用的推论；脱敏忙闲继续使用独立query，未把详情数据转成忙闲数据。
- 全部新时间轴节点、title、标签和闭包随`schedule-list.replaceChildren()`清除；`listGeneration`阻止旧日期响应回填，epoch/会话边界继续优先。
- `crm-zh-cn.js`由M36独占，defer先于页面脚本；只读`window.PhilosopherCRMText.enums`/`.timeline`/`.errors`/`.icsActions`，未知值安全回退。请求、option.value、DocType和成员权限值保持原始值。
- `crm-theme.css`是canonical，CRM payload必须逐字相同。独立补丁验证：`PYTHONDONTWRITEBYTECODE=1 python frontend-patches/dark-ui/check_apply.py`。M24生产43entry→M30导航→dark-ui→localization；dark-ui的`--verify-after`在localization前执行，最终App.vue after归最后覆盖补丁。

本轮未部署或运行真实浏览器/站点测试；标准CRM构建及三页实际样式、移动端/高并发横滚与跨标签logout实测留给集成独审后的窗口。Framework登录、CRM入口HTML/PWA品牌和后续串行汉化不在这4target独立补丁中。

## d573视觉反馈后的集中修复

- Terra `visual-8a9a3322-2c35-4ada-9607-31fd4eeb0da7` 实测1280×720时主轴从y647开始。此事实说明首屏信息占位过多；后续截图超时不能证明时间块算法错误。现在实际DOM把时间轴前置于编辑区，紧凑标题、日期与时区同排；说明/筛选/自定义窗口折叠放结果后。轴视窗使用`clamp(320px, calc(100dvh - 280px), 680px)`，保持正文16px、元信息14px；初始滚动目标为首事件top−48，由浏览器按实际视窗裁限，移除旧固定480px视窗假设，保午夜与晚间事件定位。静态合同只证明结构和CSS意图，最终像素与外观仍须新截图验。
- 旧`access.js`的浮动链接白底但无文字色，继承暗色浅字；编辑器前注入的提示则写死黄底。两处改中性token与明确前景色，并保独立fallback；通知/路由/Observer去重行为由实际执行脚本的DOM替身验证，不代表真实浏览器通过。新增`access.js`必须由M37显式overlay和源码守卫，不能只接CRM CSS。
- UserDropdown仅默认logo改为自有“哲”中性小标记加3px三色点，`brand.logo`存在时仍使用原BrandLogo；不删除上游组件、资源、About或许可证。对应UserDropdown after和canonical/payload SHA须更新，安全43entry及M30守卫不变。
- Framework GettingStartedBanner的英文literal与`theme="blue"`已定位。M35只将精确`theme="gray" variant="subtle"`建议交M39文本owner同补丁合成，未并改Framework文件或文案；由实际rc2 Button/types及gray/subtle类核实，不以全局CSS强压按钮。

## 二轮短块身份补丁

Terra `visual-41366c0f-3805-47cc-bff2-ddcf313d64be` 实证主轴y264–704约440px，10分钟12px、25分钟30px及分列正确，但短块无可见标题/编号，轴下列表不满足一眼辨识。现在日视图保真实占用块高度，块旁独立24px编号按钮+细连接线；编号按横向列区间避让，不挤入短块或冒充占用。旁侧320px标题/时间/状态栏与轴同高同viewport、各自滚动；窄屏局部横滚而非缩正文。Cancelled在编号虚线、列表按钮文字及状态中明确显示。标记与侧栏均为原生button、调用原get重新核权，仍随schedule-list整体清屏。定向DOM只验节点/尺寸目标/关联编号/同级viewport与get/清屏，不冒充实际浏览器截图通过。

access白底残留的实际缓存/执行节点/级联原因仍未知，不再调色。脚本现在在one-shot返回前及annotate后刷新自己`.team-access-notice`与指向`/team-activities`的`#team-access-link`样式；先用CSSStyleDeclaration归一化，值相同不写，不观察style属性，不增Observer或权限回调。重复执行、旧样式修复、Observer只一份及同ID异路由节点不改均有回归。版本化脚本URL由M37根据最终导出SHA生成，不在这里改request/CSP或宣称缓存根因已证。

## v4活动独立页标题/导航修复

`visual-ea0e8060-8589-4c4d-af52-64117705a295` 显示活动页正文暗底浅字，但h1近黑、Framework顶栏白、owned入口白黑。代码范围核对：活动页extends `templates/web.html`，`.crm-standalone`仅内层page_content；Framework navbar在其外，旧h1/h2/h3规则无显式color，无法覆盖heading自身近黑声明；Vue `[data-theme="dark"]`变量规则不自动覆盖无该root标记的Framework页。公开固定v15.125.0源码`website/variables.scss`的headings gray900/navbar white及`website/navbar.scss`的navbar-light背景/链接声明与此一致；没有把公开tag源码或静态判断当实际v4 computed采样。

最小修复：standalone h1/h2/h3显式`--crm-text`（导入纯HTML的同类标题亦保护）；仅`body[data-path="team-activities"]`重声明canonical palette、映射Framework已有bg/fg/navbar/card/popover/border/icon变量并覆盖navbar/link/menu/hover/focus。owned入口位于body内，继续消费同palette和原fallback，脚本/路由未改。所有新nav规则限定此route，无全局important/隐藏导航，不触login、CRM品牌或日轴rail。canonical/payload逐字同源、manifest after更新；静态CSS/token与模板合同可证明代码范围及显式前背景，最终实际截图仍待下一候选。
