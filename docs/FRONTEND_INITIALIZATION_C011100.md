# C011100：CRM 初始化本地诊断边界

状态：M20 最小诊断补丁，待独审、M9标准构建及M18真实复现。**没有确认或修复M18真实初始化失败原因；没有部署。** 不修改已关闭M19任务。原账号缓存隔离说明见 `FRONTEND_CACHE_C011000.md`；本文件记录本轮临时决定和增量证据。

## C011100-D1（2026-11-03，Provisional）

目标是让下一轮真实复现得到可读、无秘密的失败阶段及首个锁页原因，不以清storage、放宽权限、自动解锁或删除数据换取通过。

已知源码链：`accountBoundary`身份失败catch锁页但resolve ready；`main`随后assertActive抛错，统一catch再次lock。旧lock每次覆盖提示，导致身份失败、后台锁页、同步插件/socket/mount异常最终都显示“初始化失败”。M19作者只读执行固定源码证实：identify未完成时hidden→visible，再返回合法身份，仍被既有永久锁拒绝；提示经历后台→身份→初始化覆盖。**这只是受控可达链，不是M18真实visibility事件或网络响应证据。** M18首次普通Sales登录失败、一次原生刷新恢复空列表、responsive设备reload再次失败；没有业务创建完成证据。

备选：采集原始exception/stack、完整网络/body或浏览器存储（泄密且内置浏览器无console/DevTools栈接口，拒绝）；改变hidden策略/延时重试（尚无真实根因，暂缓）；现有两个目标内增加白名单阶段/首因及DOM可读码（暂选）。本轮不改变hidden永久锁策略、不加遥测、不持久化诊断、不增加接口请求或新依赖。现有telemetry插件调用保持原样；不能由此声称应用原先所有遥测均已关闭。

置信度：对受控路径分类为高；对真实故障因果为未知。诊断可撤销，安全隔离门禁不可为回退而关闭。普通可逆诊断无新增必须交用户决定的卡点；任何权限体验调整须真实定位后另提最小修复。

## 实现与读取契约

只修改原7件重放目标中的`frontend/src/main.js`及`frontend/node_modules/frappe-ui/src/resources/accountBoundary.js`；仍是7 payload + 5 guard，所有before SHA不变。

- 每页只保存当前阶段和第一个锁页的阶段/类别；没有事件历史、时间戳、身份、cookie、scope、token、URL、业务正文或原始异常。传给诊断的未知阶段被忽略、未知类别映射`BOUNDARY_LOCK`。快照只读冻结。错误message/stack不读、不序列化、不打印。
- 首次lock保持原提示及未保存编辑警告，后续身份catch/main catch/会话事件不覆盖首因，也不解锁。不清除草稿或数据库/缓存存储。
- `main`在每个同步初始化步骤前标记阶段，成功mount返回后才标`READY`。DEV上下文Promise现在返回到统一catch，使异步上下文/socket/mount失败也受同一诊断和锁页路径保护；mount前再次assertActive，不让等待DEV上下文期间的锁页绕过门禁。这是诊断失败封闭边界，不是业务功能修复。
- 身份fetch仍同源、no-store、15秒AbortController；只将受控的HTTP/重定向/JSON/无效身份/超时分成固定码。一般网络拒绝归`IDENTITY_UNAVAILABLE`，不推断具体网络原因。

### 无DevTools读取

锁页或启动确认遮罩内有普通文本段`#crm-initialization-diagnostic`：

```text
本地诊断 C011100 / IDENTITY / IDENTITY / PAGE_HIDDEN
```

顺序是`版本 / 当前阶段 / 首次失败阶段 / 首次失败类别`。M18可用内置浏览器文本snapshot或截图直接读这段，不需console、注入脚本、采集网络响应或导出存储。只回报这4个白名单值、原生操作顺序（登录/刷新/设备变更）及是否锁页。**刷新前先读**，整页导航会创建新诊断。若看不到`C011100`，只能记录“无本轮诊断”，交M9核实资产版本及前置模块是否运行；不得自行清缓存或将其当作已运行本补丁。

正常页面不增加业务UI，但`html`保留四个本地属性（DOM工具可读，内置文本snapshot不保证展示属性）：

- `data-crm-diagnostic-version`
- `data-crm-init-stage`
- `data-crm-first-failure-stage`
- `data-crm-first-failure`

正常同步bootstrap为`C011100 / READY / NONE / NONE`。READY仅表示`app.mount()`同步返回，**不是路由、异步组件、后台请求或业务读写成功**。

### 阶段白名单

`IDENTITY`, `IDENTITY_CONFIRMED`, `PINIA_CREATE`, `APP_CREATE`, `FRAPPE_UI_PLUGIN`, `SPRITE_PLUGIN`, `PINIA_PLUGIN`, `ROUTER_PLUGIN`, `TRANSLATION_PLUGIN`, `COMPONENTS`, `TELEMETRY_PLUGIN`, `DIALOG`, `DEV_CONTEXT`, `SOCKET`, `MOUNT`, `READY`。

### 类别及解释

| 类别 | 范围，不是已确认根因 |
|---|---|
| `NONE` | 未锁页 |
| `IDENTITY_UNAVAILABLE` | 身份探针一般拒绝/网络不可用，未记录原始异常 |
| `IDENTITY_TIMEOUT` | 本次15秒abort触发 |
| `IDENTITY_HTTP` / `IDENTITY_REDIRECT` | 非成功HTTP / fetch标记重定向，不记录状态正文 |
| `IDENTITY_RESPONSE` / `IDENTITY_INVALID` | JSON解析失败 / message非有效非Guest字符串 |
| `SESSION_CHANGED` | cookie变化信号，不是授权依据，不记录cookie值 |
| `PAGE_HIDDEN` | 后台事件或身份完成时hidden；恢复visible不自动解锁 |
| `HISTORY_RESTORED` / `ACCOUNT_CHANGED` | BFCache / 既有跨tab或登录登出信号 |
| `ACCESS_UNCONFIRMED` | 既有权限或敏感读失败策略锁页 |
| `PLUGIN_EXCEPTION` / `ROUTER_EXCEPTION` | 对应同步app.use抛错，具体插件由stage确定 |
| `CONTEXT_EXCEPTION` / `SOCKET_EXCEPTION` / `MOUNT_EXCEPTION` | DEV上下文 / 同步socket / 同步mount异常 |
| `INITIALIZATION_EXCEPTION` / `BOUNDARY_LOCK` | 其他已覆盖同步初始化 / 未指定受控原因锁页 |

覆盖边界：static import及模块评估先于main ready回调，异常不保证能产出此诊断；`setConfig`仍在回调外。Vue内部吞获/处理的组件错误、router异步导航、异步Layout加载和socket后续事件均不等于同步main catch；没有新增全局unhandledrejection/error监听器，不拦截或转储这些异常。若停在一个非READY阶段但无failure，只能报告已到达阶段，不能据此认定那个模块已抛错。

## 精确构建交接

权威清单仍为 `frontend-patches/c011000/manifest.json`，固定CRM HEAD `36bd8859f2a6345a620477bc708d0546e8c3f08a`及原before/guard SHA完全保留。当前增量after：

| 目标 | after SHA256 |
|---|---|
| main.js | `020c49ea9c8104d2e26fbf81ab842d849b4ceec018867c59c1ee76df9dce59d1` |
| accountBoundary.js | `a3db2ba7b48f2b6581a89addb4d6ca8a089b048a81dbe5275099fa97dee54dac` |

1. 独审精确tip通过后，M9将本tip的完整`frontend-patches/c011000`复制到新的隔离构建上下文。实际应用文件集合仍是`apply.py`, `manifest.json`, `payload/**`；测试交接新增`initialization.test.mjs`、`real-runtime.test.mjs`，保留原controlled、三个consumer-fixtures及更新bridge。不能向已应用M19的树重复apply，须从匹配原before SHA的固定干净构建层开始；不能调宽guard或用force。
2. 在该隔离固定CRM树执行`python "$PATCH/apply.py" "$CRM" --check`，然后同命令去掉`--check`；逐目标核after。沿M9现有标准preseed/`bench build --app crm`/manifest强断言流程，不改共享容器、运行站点或Framework映射，不重装frappe-ui。M17公开39件导出不含完整node_modules，不能单独构建。
3. 在完整固定frontend中执行标准`yarn test:run`；复制本tip bridge到隔离`frontend/tests/c011000.test.js`，设`C011000_PATCH_DIR`再跑`yarn test:run tests/c011000.test.js`。更新bridge有2项：第一项内跑18+6受控场景；第二项以frontend cwd为`C011100_FRONTEND_ROOT`执行下述真实Vue/Pinia内存renderer烟测，不把它包装成真实DOM/browser验收。记录补丁tip、receipt、manifest、完整构建/标准测试结果与新镜像ID；失败不部署。
4. M9统一构建后由tower协调本地部署及M18复现；M20不部署。M18不要清IDB/storage/cookie或注入登录会话。原生Sales登录、原生刷新、responsive设备reload逐步读诊断；额外区分是否出现hidden/BFCache/跨tab操作。若复现失败，先回传本地码再商议修复，不自动调整hidden或权限。成功加载后仍需原权限虚拟数据UI/API深测，不拿空列表或READY当通过。

## 本轮验证

Windows Node v22.20.0 / Python 3.14.0。无新增依赖、未运行构建或部署。

```sh
node --experimental-vm-modules --test frontend-patches/c011000/controlled.test.mjs frontend-patches/c011000/initialization.test.mjs
node --check frontend-patches/c011000/payload/main.js
node --check frontend-patches/c011000/payload/resources/accountBoundary.js
```

24/24通过：原18项正常路由、账号缓存防御全部保留；新增6项覆盖实际main完整同步顺序与DEV正常路径，11个同步阶段抛错及DEV异步失败，真实browserEnvironment的HTTP/redirect/JSON/shape/Guest/网络/超时分类，identify期间hidden→visible首因保留、cookie变化/无事件hidden、未知诊断值拒绝与无秘密输出。此组执行实际main+boundary源码，但Vue/Pinia/plugins/App/DOM/fetch仍是替身。

严格重放另已通过：`python -B frontend-patches/c011000/check_apply.py "$BASELINE" "$RUNTIME"`，BASELINE为前述M17固定公开导出根，RUNTIME为工作树内临时ignored空目录（运行后清理）。匹配7件after、dry-run零写；漂移/缺文件/错误HEAD/重复应用拒绝且拒绝零写。7 payload SHA/LF与5 guard集合检查、JS语法及`git diff --check`均通过。

### 固定真实Vue/Pinia烟测

M9仅从既有已停止network-none probe只读docker cp，未start/exec/install/HTTP，导出公开运行时闭包到：

`P:/CRM/.tower/worktrees/wt-9/deploy/.runtime/m20-public-frontend-evidence-3828e3eb572143f99e2420809fd5f1b2`

来源index `sha256:f43a277d62eab434ba90922f36b8a75e86a99a7d0dbdede1cbb70bbe57783a6d` / config `sha256:50836b19cb4ac574f53840c100123f87f19032c22788cbd63b12f2146537a69d`。`runtime-closure-manifest.json` SHA256 `e162f4cb7dcace668e83a64bcac57cca6d6d3031a7170122aeed7b6ffbd86672`，本轮再次逐件核665文件bytes+SHA一致；26个现有运行时包约17.2MB。真实版本Vue/@vue 3.5.32、Pinia2.3.1、vue-demi0.14.10。源/原测试另由M9公开清单保存，非完整开发依赖树，不随补丁分发第三方包。

在Git Bash实跑（路径换作仍有同一固定运行时的只读目录也可）：

```sh
C011100_FRONTEND_ROOT='P:/CRM/.tower/worktrees/wt-9/deploy/.runtime/m20-public-frontend-evidence-3828e3eb572143f99e2420809fd5f1b2/apps/crm/frontend' node --experimental-vm-modules --test frontend-patches/c011000/real-runtime.test.mjs
```

1项测试内4路径全部PASS：执行实际main、boundary和session payload，使用真实Vue `createRenderer().createApp()`、Pinia `createPinia/install/defineStore`、Vue `ref/computed`。身份等待期间零App创建/零setup；合法Sales确认后真实Pinia先install，实际session store在setup运行1次，computed与store注册正确并mount出内存host节点；Guest及identify期间hidden→visible后零setup/零节点；真实Vue `app.use`中的受控sprite插件抛错正确归`PLUGIN_EXCEPTION`。

此组不是runtime-dom浏览器mount：host是内存替身，根组件是仅调用实际sessionStore的受控组件，resource创建、FrappeUI/router/translation/telemetry/socket以及网络/页面事件仍是替身。未运行真实App.vue及异步Layout、完整FrappeUI provider、真实router install/navigation、浏览器CSS/后台时序或业务权限写读。它核验真实Vue/Pinia启动顺序可工作，不能证明M18实际根因，也不能替代完整CRM初始化。

原M9基线的34文件326原生测试及旧bridge18项通过只是旧tip证据，不能转称本tip标准测试已过。当前host只有约24.5MB公开源码/运行时子集，完整开发node_modules约417.7MiB仍只在固定已停止probe/镜像内，不能擅自启动旧probe或增装依赖凑测。本tip原生Vitest（含更新的2项bridge）、标准Vite资产构建、真实Vue/Pinia完整CRM初始化及M18端到端保持M9/M18后继门槛。
