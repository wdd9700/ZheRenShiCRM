# 本轮浏览器直接观测记录

所有记录均为本轮工具返回内容的人工摘录（不是原始网络录制或截图）。时间为 Windows +08:00。未复制密码、Cookie、令牌或站点配置。snapshotId 仅用于回查本会话工具转录，不是永久可点击证据。

## E01：入口，约20:43–20:44
- 内置浏览器初始 `panelVisible=false`，无标签页。
- 打开 `http://crm.localhost:8090/login`：`NAVIGATION_FAILED / ERR_CONNECTION_REFUSED`；其后标签页状态含 `The page process stopped unexpectedly`。该浏览器错误不等同服务端根因。
- Windows TCP补充探测：127.0.0.1:8090 timeout，18088 connected，8088 timeout。与浏览器错误属于不同观测，不能合并为精确故障诊断。
- 打开 `http://127.0.0.1:18088/login` 后，跳转 `/crm/leads/view/list`。继承已有内置浏览器合成会话，页面显示 `C010900 TEST A`。本轮尚未重新验证该账号口令/服务端角色。
- 匿名 GET `/api/method/ping`：HTTP200，application/json，正文 `{ "message": "pong" }`（实际有换行）。
- 本地主checkout HEAD `7962e5d9415eeb701382a58e246e71b6e7b961c3`，不代表在线站点版本。

## E02：初始线索列表与创建弹窗
- snapshot `text-761505cd-4b47-4da7-b3f2-40a6fe1fbebf`：显示导航、线索列表和6条合成记录，含负责人B命名的历史记录及Administrator历史记录；未证明这些记录是否已授权共享，因此不据此定越权。
- `elements-294eaaa1-ad67-4203-b5d8-b6ea7b631ab0`：全名筛选输入已有值 `C010900 TEST`，筛选器计数1。该初始状态不用于证明当前筛选正确性。
- 点击“创建”后，`text-b610a287-de07-421f-b12f-2b5c37ccd2fa`见“创建线索”、必填名字/状态、负责人C010900 TEST A。
- textbox扫描返回的只是列表筛选框，`scanTruncated=true`。不能可靠定位弹窗必填字段/最终创建按钮，因此未确认提交。
- `page.visual.snapshot`耗时10秒后返回`PAGE_NOT_READY`；未为截图打开前台面板。

## E03：组织查询、弹窗草稿和既有详情
- 正常侧栏点击组织，文本显示4条历史合成组织。
- 输入组织查询 `QA-FORK-20261103`，后续页面见“未找到组织 Clear the filters to see all records.”。
- 点击“创建”，在弹窗“组织名称”输入 `QA-FORK-20261103-ORG-合成企业`，Company Description输入“仅供浏览器验收的合成资料，不代表真实客户。产品：设备巡检；需求：缺陷识别试点。QA-FORK-20261103”。输入值经元素快照核实。
- `text-59a102f4-88de-4a8d-a2c4-1cf93ece0f0e`、`text-1b0dd7ee-3bfa-4d61-a4ad-f9afc24a23d2`：弹窗存在；元素扫描截断，无法可靠取得底部提交按钮。尝试普通Enter、ShiftTab/Enter后未见成功，最终Escape关闭；重开时草稿保留。未判定已创建。
- 清空组织查询，正常点击历史列表项 `TEST-C010800-TEAM-20261102163350合成企业`。
- `text-dc5b0193-cfb6-46ec-bada-1c8a5ce5d4ee`：真实详情面包屑、组织名、New Deal、详情、商机0、联系人1、空商机提示出现。未修改历史记录。
- 页面组织简介字段下出现长篇Note/Task共享说明，属于可观测文案位置；是否是预期统一提示需要产品确认，不作为权限漏洞证据。

## E04：联系人列表、无结果查询及创建草稿
- `text-8ae5cf21-ad82-4c39-97e2-e7f2855e0561`：联系人列表20/20，包含合成组织关联与测试A/B联系人；只读观察，不推断私域规则。
- 电子邮件筛选输入 `qa-fork-20261103@example.invalid`，`page.wait_for`确认“未找到联系人 Clear the filters to see all records.”。
- 点击“创建”，`text-d9195a6e-170f-4bae-b57d-f227ca0dc023`显示“新建联系人”、名字必填、邮箱/手机号/公司/职务等字段。
- 在可定位的名字输入 `QA-FORK-20261103-合成人员`。其余字段/提交按钮扫描被截断，Escape取消，未确认任何保存。

## E05：任务列表和新建草稿，约21:00
- 正常点击任务导航，`text-e7f45b3c-eb5c-4c5a-9923-6c94d49ff0c9`见任务/列表、创建、优先级/负责人/状态/筛选器/排序/列；没有记录行或明确空列表说明。仅记录该表现，不确定是否请求失败。
- 点击创建，`text-59136f41-d885-43c7-a82f-46495deb3d59`见“Create 任务”、标题必填、描述、优先级低、截止日期、负责人、状态待办事项和创建。
- 标题草稿 `QA-FORK-20261103-跟进合成需求` 输入成功；底部提交控件无法可靠定位。ShiftTab/Enter后弹窗关闭，`text-04f23168-3dde-4b38-9ea7-d9cdab9a766b`仍仅列表框架，无成功提示/新增行。未把它计作创建成功。

## E06：活动普通表单保存失败
- A账号通过底部“活动私域/共享管理”进入 `/team-activities`，列表“可读活动：0”。页面明确无父记录只能Private，Shared仅扩展父记录读者。
- 新建Private活动，标题 `QA-FORK-20261103-PRIVATE-NOTE-A`；正文为合成缺陷识别需求，带字面文本 `<b>合成内容</b>` 和逗号；类型FCRM Note、无父记录、Private、协作者空。
- 点击实际保存，`text-d7bef012-79ab-4bbc-838b-a6a7816f76df` 显示“请求被拒绝或失败；未保存。请检查授权和父记录。”。`elements-b81280cf-ccde-4817-ab82-2ff0bea6f3e2`核实表单上述值。没有HTTP状态/响应证据，根因未知。
- 改Shared并保存，原生发布确认对话框accepted后仍同样失败（`text-9178a9b3-1f70-45c0-82a0-42c3f9e20b15`）。不能据此独立证明无父Shared验证正确，因为Private正例也失败。
- 离开再进后列表仍0、表单空。没有确认成功写入，但未查数据库，不能宣称数据库零写。

## E07：身份与导入权限
- 同浏览器辅助GET `/api/method/frappe.auth.get_logged_user`，`text-730c1956-57ab-4cf8-9578-63273302b9d4`返回 `c010900-test-202611030044-a@example.invalid`，确认A服务端身份；未读取角色列表。
- A进入 `/resource-import`，`text-da980aba-c155-4942-a4da-6e040bebd109`显示“不允许 / 无资源导入权限”。这是入口拒绝，不等于所有导入API负例覆盖。

## E08：列表与详情权限不一致、筛选不匹配
- A新开CRM标签，六条列表仍含 `TEST-C010800-TEAM-20261102163350B`。实际点击首行进入 `CRM-LEAD-2026-00009`详情。
- `text-b6741a0e-e796-40ea-bb62-3448e010bc2c`显示“Error occurred / 控制器权限检查未通过 用户c010900-test-202611030044-a@example.invalid无此文档访问权限: CRM线索 - CRM-LEAD-2026-00009”。这是同一身份列表可见摘要而详情拒绝的直接证据；未判定是服务端列表授权还是前端缓存问题。
- 返回后清空全名，再正常type_text输入 `TEST-C010800-TEAM-20261102160603`，`text-ff4be801-9096-48a3-8435-5a510c376d40`仍六条不匹配记录。
- reload后，`elements-fa05dd2a-1419-45e3-a587-949880da7919`确认筛选值保留，`text-3f400fb6-e14d-4223-8e0d-ed1ff68dc64a`仍六条。不是仅依据一次fill行为判断。

## E09：注销、跨标签残留、错误登录与管理员登录
- 原生网站菜单注销，`text-d5068813-4291-4809-8442-f9ea73b5c0c0`显示“您已成功注销”。
- 此时另一个已打开CRM标签未经刷新仍显示A与六条旧记录（`text-cb3d1e44-4e0e-4c94-ad4c-fae29ce8964f`）；没有在该标签发送业务查询，不据此宣称匿名还能读服务端。
- 已注销会话GET身份接口，`text-649b44d8-6746-45d3-9c4e-bd1b5e4861cd`显示“不允许 / 权限不足 / 状态403”，确认服务端已注销。
- 正常登录表单使用一次不存在的合成账号，`text-202c0ec0-69fa-4a8e-bf61-d0252028214f`显示“登录无效，请重试”；未做暴力/限流测试。
- 再用用户已有Administrator凭据正常表单登录，跳转CRM，`text-a01facbe-e6fd-483a-9cf7-adf7696ff35c`显示Administrator。相同全名筛选此时只显示一条匹配记录、1 of1。未将凭据写入本报告。
- 浏览器标签共享认证状态，不是隔离A/B浏览器上下文。本轮尚无B账号登录、撤权或完整权限矩阵。

## E10：其余入口与公开资源指纹
- 商机页只有列表框架，没有行或明确空态（`text-8cf1d828-2214-439b-b6fa-9f3789333b34`），原因未确定。
- 数据面板真实展示过去30天线索0、商机0和No data to show（`text-1b16e48c-58c2-4997-957d-683d4321570b`）；范围/权限不同，不能只据此认定计数错误。
- 备注明确“No notes yet”，新建弹窗可开，后点击关闭取消。关于弹窗仅产品和帮助链接，未展示可用版本号。
- CRM reload/新标签再次出现Getting started。本轮只Close未Skip all，不能认定完成引导后仍弹窗。
- 匿名 `/login` 200；四个HTML实际引用的公开资源均200。资源SHA仅用于比对，不代表镜像或commit：
  - website.bundle.M7Z35CSX.css：450560 bytes，`fd9e6c46dd6123a9dca794e2a16d58b10321df820eec243e634e444bd018f610`
  - login.bundle.J7LAEDYF.css：32354 bytes，`9473c5c96d09ab54e1355c8b27a1a74a9cad262eda50a8df7b1687b80f454148`
  - frappe-web.bundle.ZHGNNN4K.js：834301 bytes，`ff162d4047242201880a50b05eb021023194daee7aa7b6e4d56882b3d96fcbea`
  - /assets/team_access/access.js：2058 bytes，`d58975d96cd65f2bbc7866b5d8ceb37ee508e9e810f5107c921cd21b404cad88`
- 另一次匿名GET `/crm`得到HTTPError但未记录status，不作为服务不可用结论。

## E11：管理员真实CSV导入闭环，约21:27–21:29
- Administrator表单登录后进入 `/resource-import`。未勾选共享确认时预览disabled；选择本目录 `qa-fork-import.csv`后仍disabled；勾选后可预览（`elements-cf878057-e1e5-4ca2-a0f6-0a005fc5cc68`）。
- 文件通过页面文件控件和浏览器file dialog上传，不是API代提交。共3行：唯一有效资料、相同资料不同序号、缺姓名。产品与需求含中文/逗号，联系方式为@example.invalid。
- `text-9d12d591-b433-4393-aaf1-3ef25cf47025`：预览3行/错误1，逐行为新建、文件内重复、缺少姓名；表内中文和逗号原文保留。最终确认checkbox未勾选时应用disabled。
- 勾选最终确认并点击“确认导入有效行”。`text-f9c702be-ecd1-49ab-b651-2c561e14f57f`：
  - 来源行2，序号1：成功；Lead `CRM-LEAD-2026-00010`，企业 `QA-FORK-20261103-ORG-合成企业`，联系人 `QA-FORK-20261103-合成人员-QA-FORK-20261103-ORG-合成企业`。
  - 来源行3，序号2：已导入，复用相同三个对象链接。
  - 来源行4，序号3：失败，缺少姓名。
- 页面成功后最终确认自动清空、应用disabled。
- 点击“下载失败行CSV”，browser下载记录completed/277bytes；保存 `C:/Users/74090/Downloads/resource-import-failures.csv`，Read核对八列（原六列、来源行号、失败原因），唯一数据行为缺姓名的第4行。未测危险公式前缀；不能用页面防护文案代替验证。
- 通过实际结果链接点击Lead，进入 `/crm/leads/CRM-LEAD-2026-00010`。`text-d2a7c43c-b794-44ed-9e33-3ceb12ffc155`见线索/QA-FORK-20261103-合成人员、Administrator负责人、新建状态、转换为商机、活动页及明确对象编号。不是只看HTTP200或CRM外壳。
- 详情字段标签可见，但本轮未取得产品/需求持久化字段值，只有预览原文保真和对象创建回读通过；未把完整存储保真、再次上传幂等性算作通过。

## E12：管理员关联新Lead的Private保存仍失败，约21:30
- `/team-activities`初始Administrator可读活动12（是管理员视角，不作为普通用户越权证据）。
- 新建Private，标题 `QA-FORK-20261103-PRIVATE-NOTE-ADMIN`，正文为带本轮标记的合成沟通，父类型CRM Lead，父编号 `CRM-LEAD-2026-00010`，协作者空。
- `elements-99c53acf-88d6-4113-a1e0-caf4b1c30034`核实上述所有值；实际点击保存后 `text-ada536f9-b3ae-4f19-82c8-b86785575019`仍显示“请求被拒绝或失败；未保存。请检查授权和父记录。”。
- 因此问题不只出现在A无父记录场景；仍未取得网络错误状态，不能宣称已定位具体后端原因。

## E13：跨标签账号变更残留与最终退出
- Administrator已成功登录后，未刷新旧A标签，`text-d9c2ad3c-8875-4933-b172-4aef359fbb61`仍显示C010900 TEST A与旧六条列表。没有将其解释为独立账号会话。
- 本轮结束正常点击原生网站菜单注销Administrator，`text-1156d40f-3083-42b1-a5e5-35d05390ce88`确认“您已成功注销”。未清理全站storage、未重置A口令或全局撤销其他会话。

## 工具限制与影响边界
- 多次 `page.elements.snapshot` 在指定角色过滤、viewport/document范围及提高返回数量后仍 `scanTruncated=true`，且没有nextCursor。不能把“工具拿不到ref”定为应用按钮不存在。
- 隐藏面板截图超时，不使用桌面鼠标、用户Edge、切换可见标签或激活面板来绕过“不影响前台”约束。
- 所有输入均合成资料。本轮确实通过导入创建了上述三个业务对象；其他创建草稿/活动失败没有成功保存确认。未删除记录、未部署、未改权限或服务。
- 下载失败CSV作为验收产物保留在Downloads；仓库之外没有手动编辑文件。没有发送邮件、富化外部查询或触发真实客户联络。
