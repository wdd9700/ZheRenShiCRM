# C011000 CRM 账号缓存隔离构建补丁

状态：构建补丁与受控测试交付，待独立审查；未运行标准Vite/Vitest，未部署、未通过真实浏览器验收。仅修复正常账号切换的防御性缓存边界，不扩展漏洞探索。

## C011000-D1（2026-11-03，Provisional）

目标：身份尚未由服务端确认时不展示历史业务缓存，切换身份与权限失败不恢复旧账号业务数据。不删除任何业务记录、IndexedDB、认证数据或用户偏好。

已知：M17只读导出运行CRM HEAD `36bd8859f2a6345a620477bc708d0546e8c3f08a`，frappe-ui `1.0.0-rc.2`；具体文件内容另以SHA256固定。运行实物含abort、getChangedFields等实现；未与npm原包完整比对，不推断修改来源。资源local模块默认持久业务数据；generic资源失败previousData回填，内存key无身份。

备选：仅加user key无法处理同账号撤权；尾部HTML注入清库不能保证早于模块/异步回读且破坏存储边界；本轮暂选构建期固定源补丁，禁资源持久读写、每页不可迁移内存域、可信服务端启动门禁、失败不回填、身份信号后遮罩。

保守实验限制：后台标签恢复后暂不自动解罩，要求显式刷新；提示刷新会放弃未保存编辑，提供标准登录出口。旧草稿仅留原页面内存，不跨身份显示/提交，不自动清除或搬迁。此限制明显影响多标签工作流，不视为最终团队体验；同身份业务权限重验及草稿恢复需另做设计、真实UI验证。选择明确安全边界而非仅核同身份后复用可能已撤权数据；不高频轮询、不逐资源额外核身份。

置信度：受控回归通过，仍需独审；真实浏览器、构建集成由M9/M18验收。无新增必须交由用户决定的授权卡点。可逆性为构建补丁与旧镜像保留；不得为回退而暴露已知跨身份缓存问题。

## 实现边界

- `accountBoundary.js`在资源模块评估时建立遮罩；独立原生`fetch`以`credentials: same-origin`、`cache: no-store`、15秒超时调用`frappe.auth.get_logged_user`。Guest、网络错误、重定向、启动中cookie变化一律不挂载CRM。`session.user`来自该响应，不从`user_id` cookie推导身份。cookie仅作为变化信号，不是授权依据。
- `main.js`同步配置原有`frappeRequest`，待身份门禁通过才初始化Pinia/router/socket并挂载；业务资源请求也等待门禁。资源fetcher在等待后取配置，避免模块初始化的auto请求绕到普通request。发送前、异步校验后、结果回调前均检查边界，旧响应不能触发success/data回调。
- 内存cache key带当前页面随机域；该域不跨页面迁移。账号登录成功强制整页导航，登出广播后前往原生登录；不在同一旧应用树中更换身份后复用store。遮罩不自动解除。旧store/草稿留原标签内存但不可见，不作为新身份缓存。
- `local.ts`三个适配器均为no-op；移除三个resource的异步持久回读路径。已有IndexedDB内容仍保留，但本补丁不读取、不写新业务值、不调用delete。未调用`indexedDB.deleteDatabase`、storage.clear或通配删除。用户偏好、认证存储不动。
- generic请求错误将data/previousData清空，禁止previousData回填；list错误还清originalData/dataMap；document读取错误清doc/originalDoc。document保存失败不回滚旧快照：普通校验错误保留正在编辑的本地草稿，权限失败则遮蔽整页，避免静默丢草稿或恢复敏感旧doc。
- HTTP401/403、PermissionError/AuthenticationError/SessionExpired锁页；已知列表/详情读取失败也锁页，不能离线回填。正常DoesNotExistError清空文档但不锁整页，避免正常删除后的预期refetch妨碍导航。遮罩含显式刷新、原生登录链接和独立原生POST logout按钮；logout失败继续遮蔽并可重试，不依赖已经锁住的业务资源。
- 浏览器后台`visibilitychange`、BFCache `pageshow.persisted`、跨标签BroadcastChannel会话变化均锁页；focus和请求边界额外比较cookie变化。浏览器不支持BroadcastChannel时仍有后台/focus/请求边界，不承诺所有并排标签的即时感知。未加高频轮询。

### 明确保留的限制

1. **不是即时远程撤权系统**：前台无新请求、无焦点/后台变化且无广播时，无法感知服务器单独撤权。收到权限失败后绝不复显旧业务值；重新打开/刷新从新服务端请求开始。同账号权限重验不能只用get_logged_user代替。
2. 后台恢复需显式刷新；用户必须接受文案中“放弃未保存编辑”。不自动刷新、不自动保存旧草稿。正常多标签工作体验尚非最终可用承诺。
3. 不取消已经到达服务器的在途写请求，不声称实现服务器事务撤销；服务端权限仍是最终授权边界。原生直接`call`等非resource调用不因本补丁变成授权机制，锁页时整个旧应用被隐藏且不接受正常交互。
4. 旧IndexedDB字节未清理。本轮是正常账号切换防御，不是本地恶意脚本/开发者工具隔离或设备取证擦除。
5. 仅覆盖已核CRM使用的v1 resource模块，不泛化为frappe-ui全部v2组合式API、其他应用或所有浏览器缓存。不能把本次补丁断言为M18六条旧Lead页面的完整因果证明。

## 固定基线和精确重放

来源：M17只读导出自镜像config ID `sha256:fb00dd79167160c4e00d9678ff7df3f59c8e86a932e029384112145fc8a134ae`，CRM HEAD如上，frappe-ui rc2。证据目录（仅本机ignored材料，不是分发依赖）：`P:/CRM/.tower/worktrees/wt-17/deploy/.runtime/m19-fixed-frontend-evidence`，39文件manifest与SHA256SUMS。frappe-ui lock项为`https://registry.yarnpkg.com/frappe-ui/-/frappe-ui-1.0.0-rc.2.tgz#03e2c8be7d9e18cd2a0c4d09b78df91d37bd81bb`，integrity `sha512-sLsoWGmgzhdeyfOmwzDwD5ZrJh3VZ0mA2a7lf9rwxyYCfZKSGAp/qXSO002+CbVuIWqYA3sGuPbl9Dn2+m1n/A==`。这不是npm原包与运行树一致性的完整证明。

权威重放清单是`frontend-patches/c011000/manifest.json`，包含7件前/后完整SHA256，另锁frontend package/yarn.lock、frappe-ui package/request/frappeRequest。`before: null`的新accountBoundary必须不存在。`payload/`是完整目标文件快照，用严格替换避免模糊patch偏移；保留上游文件其余语义和现有许可证，不把第三方实现冒充自研。CRM两件源沿上游AGPL-3.0，frappe-ui相关实现沿其MIT；分发时继续保存对应源码及原上游许可。

在**隔离构建副本**、既有依赖完整且尚未改这些文件时执行（PATCH为本补丁绝对目录，CRM为固定CRM源码根）：

```sh
python "$PATCH/apply.py" "$CRM" --check
python "$PATCH/apply.py" "$CRM"
```

拒绝条件：CRM HEAD不符、任何锁文件/源hash不符、缺文件、目标符号链接/硬链接、父路径逃出CRM、payload hash漂移、重复应用。检查全部通过前不写目标；应用阶段每件临时文件+replace，但不提供多文件原子事务：若磁盘/权限中途故障，丢弃该构建层，重建干净副本，**不能继续从半补丁镜像运行**。不提供`--force`或模糊匹配。不要在运行容器/共享源码上执行。不要将“版本号相同”当逐件hash相同；禁止为通过检测而刷新manifest到未知基线。

## M9依赖与构建交接（尚未执行）

1. 独审通过后，由M9使用已核固定镜像的完整Linux CRM+依赖树，在独立构建阶段继承或从该阶段复制`/home/frappe/frappe-bench/apps/crm`（含frontend/node_modules）和匹配Framework树；以inspect核定实际镜像ID，不使用移动tag。M17的39文件导出不包含完整node_modules，**不能拿它单独完成Vite构建**。
2. 如果M9选用现有`bench get-app`/依赖安装流程，必须在该流程完成后先跑`--check`；只有锁及实际源码hash完全一致才能继续。若不同则停构建交tower/M19重新核适配，不改共享上游、不用`yarn install`覆盖后假装同基线。离线依赖来源为固定镜像现有树，本补丁不新加包、不下载额外依赖。应用之后禁止重装frappe-ui。
3. 将已审`frontend-patches/c011000`带入构建上下文并按上节应用；再沿现有Framework资产preseed/`bench build --app crm`/manifest强断言流程构建，不改Framework映射、不绕开既有资产校验。deploy归M9所有，本次未改Dockerfile。保存CRM HEAD、补丁commit、manifest及镜像ID。应用或构建失败不部署。
4. 标准回归需要完整frontend依赖：在CRM/frontend跑`yarn test:run`，并执行标准CRM assets build。另可把`vitest-bridge.test.js`复制到**隔离副本**`frontend/tests/c011000.test.js`，设置`C011000_PATCH_DIR`为完整补丁绝对路径后跑`yarn test:run tests/c011000.test.js`。bridge只把同一受控Node测试挂入现有Vitest，**不升级为真实Vue/浏览器集成覆盖**；此bridge及标准Vitest在本次均未实际执行。M9如已有原生resource测试，须并跑，不能仅以bridge代替原有测试。
5. M9统一构建后，M18真实UI验收：管理员正常注销→Sales A原生登录；保留旧IDB、不清库；列表/详情无管理员旧值；受控失败/离线与同账号撤权；前后台/双标签/BFCache；未保存编辑提醒；锁页logout与重新登录；正常列表分页、详情保存、删除后导航及校验错误草稿仍可处理。检查启动网络门禁先于业务展示、无旧success回调、无敏感数据闪现。须在固定新资产上验，不能只凭200页面壳。

## 已执行的受控验证

执行环境：Windows Node `v22.20.0`、Python `3.14.0`。未安装依赖、未构建镜像、未操作远端。

```sh
node --experimental-vm-modules --test frontend-patches/c011000/controlled.test.mjs
python frontend-patches/c011000/check_apply.py frontend-patches/.runtime/baseline frontend-patches/.runtime
node --check frontend-patches/c011000/payload/main.js
node --check frontend-patches/c011000/payload/session.js
node --check frontend-patches/c011000/payload/resources/accountBoundary.js
```

首轮13项通过（R1修复后全部重跑仍通过；当前合计18项，新增消费者回归见下）：

1. 服务端身份而非cookie身份；Guest/离线启动继续遮蔽。
2. 正常generic列表、同页cache、document详情；正常删除后的DoesNotExist清空不锁整页。
3. 持久适配器不读旧值、不写/删存储；源码断言无IDB/storage调用。
4. 普通请求失败不恢复generic previousData。
5. 同账号403撤权清旧generic data并锁页。
6. list失败清data/originalData/dataMap。
7. 管理员→Sales A的新页域不同；异步旧响应不调用success、不赋旧值。
8. 后台/BFCache/跨tab信号锁页，不自动清除外部草稿。
9. 锁页后session login/logout端点可调用，身份变化广播。
10. 异步validate期间账号变化，阻止后续网络提交。
11. document普通ValidationError保留本地编辑，不恢复旧服务端快照。
12. 实际browser adapter在DOM替身中验证no-store同源身份请求、遮罩及独立带CSRF logout出口。
13. 实际CRM session模块在Pinia/Vue替身中使用确认身份；logout清session user/广播/前往登录，login成功完整导航而不复用应用树。

Python重放测试：真实固定导出内容复制到工作树ignored临时目录；只mock `git rev-parse`来分别供给匹配/错误HEAD，不伪造文件hash。确认dry-run零写、7件输出精确等于after hash；漂移/缺失/错误HEAD/重复应用均拒绝且拒绝不写。临时fixture自动清理。

替身边界：Node VM执行真实补丁resources/list/document/session/boundary源；Vue reactive/watch/effectScope、Pinia defineStore、fetch配置、DOM、BroadcastChannel/realtime/socket采用受控替身，local.ts仅剥类型签名，不是TypeScript编译检查。多数场景注入boundary环境，第12项才执行实际browser adapter但仍是DOM/fetch替身。没有真实IndexedDB、CSS渲染/可访问性、网络服务端认证、真实权限修改、真实导航、真实后台事件时序或完整业务UI操作。未运行Vite、原生Vitest、浏览器或生产验收；这些保持M9/M18后继门槛。

## R1审查返工（2026-11-03，补丁待重审）

保留原R1记录与提交`1c66c7fe7274655388ffb0a709ed4ef18f85cfad`，不覆盖旧审查。R1的`p2-1items`成立：新增`await accountBoundary.ready`后，auto资源同步返回时`resource.promise`仍为null。固定router会立即await users.promise/views.promise，因而跳过真正的get_users/get_views等待，正常Sales深链接可能误跳Not Permitted，Home或列表可能漏选默认视图。原13项只await fetch返回值，不足以验证真实消费者契约。

修复：公开fetch不再为async；每次调用同步创建并发布完整runFetch Promise，再原样返回该Promise。Promise仍先等待可信身份门禁，继而请求、transform、同步success/data回调及错误处理；不再把out.promise替换为裸网络Promise。fetcher仍在门禁之后取配置，不绕过账号校验。每个Promise内部附一个拒绝观察器，避免auto调用者忽略返回值时出现unhandledRejection；原Promise本身仍拒绝，router或调用者await时能收到真实错误，不通过吞错假装成功。回调返回的任意异步副作用保持上游语义，不声称被资源Promise追踪。

并发策略：每次实际fetch增加generation，旧generation在门禁后、发送前、transform前后及每个回调前失效；旧成功/旧失败均不能覆盖新结果或清除新loading/error。回调同步重入fetch时新Promise保持为out.promise，旧请求停止后续回调，finally不复位新请求loading；被替换/显式abort的旧Promise以AbortError拒绝且已有内部观察器。显式abort同时使generation失效，避免不遵循AbortSignal的替身/传输回传旧值。已有debounce调度语义未扩展：本次修复的是固定users/views等非debounce auto资源同步发布契约，不承诺debounced函数在计时器触发前已经创建网络Promise。

### 新增固定消费者回归

`consumer-fixtures/{router.js,users.js,views.js}`逐字复制自同一M17固定公开源码，**仅测试输入，不应用到CRM业务树**；脚本读入时校验SHA256：

| 文件 | SHA256 |
|---|---|
| router.js | `5978786c44b5a79a506e8316aa8f2c3db844d558d575b02bfbc6da76f4db9f6b` |
| users.js | `9e2b275acbb20a495168b3c1b22f4dbf1f48b7acb9c86f6f8b6770a96d46009d` |
| views.js | `cd7967d37f0e5dccab8a89019c258a5554248b33860be60708c038fb178e553a` |

在原13项上追加5项，当前18项全通过：

14. 执行真实固定router/users源：延迟get_users时立即可见稳定promise，守卫不提前next；授权Sales返回后保持原Lead ID和`#activity`深链接，不转Not Permitted。
15. 执行真实固定router/views源：分别验证Home、Deals列表在延迟get_views时不提前next；返回自定义kanban默认视图后精确选择其路由/参数/query，而非默认Lead或list。
16. 身份门禁未完成时资源Promise已发布但零业务请求、守卫等待；Guest或身份探针离线后Promise拒绝、next(false)、无业务请求/数据、不解罩；延迟确认Sales身份后才发请求并保留深链接。已确认账号的get_users网络离线next(false)，get_views离线使守卫Promise拒绝且不next，均无旧数据或误选默认视图。
17. 并发旧成功不写回；旧403失败不清新数据、不锁新状态；success回调重入后旧onData不运行、新Promise及loading保持；显式abort后即使传输仍返回也不写旧结果。
18. auto请求的网络、transform、同步onSuccess三类拒绝在故意延迟消费时无未处理拒绝，但原已发布Promise仍拒绝并清旧data。

执行器仍为同一Node VM harness，router.beforeEach/get_users transform/get_views transform/getDefaultView均来自固定实物，**不是手写等价守卫**。Vue/Pinia/vue-router运行时、后台idle调度及网络依然受控替身；这是修复消费者竞态的源级回归，不升级为浏览器验收。

重放接口、7目标+5guard集合、固定before SHA保持不变；只有resources.js的after SHA更新为`17b8bef0cc7f5bc4232c8edf7bd93d404a52d94dfa428230052eca15efa5e6d4`。测试交接文件集合新增三fixture，M9导出测试上下文须带齐，但实际Docker应用仍只需apply/manifest/payload。重跑原13项、新增5项、Python重放拒绝、语法及LF payload hash检查后提交新tip，须新一轮独审；标准Vite/Vitest/真实UI门槛与所有实验限制不变。
