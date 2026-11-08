# 哲人石CRM Windows 桌面客户端 W020

## 决策（2026-11-08，实施前暂定）

- 用户明确要求真实 EXE 安装包、覆盖升级保留客户端数据并预留 OTA。Windows 优先，复用集中 CRM Web，不另建业务数据库。
- 暂选 Electron 45.2.3 + electron-builder 26.18.0 + electron-updater 6.8.11；Node 22.20.0 / npm 11.6.3。备选 Edge PWA 不能提供独立 EXE/NSIS；Tauri 增加当前未验证的 Rust/WebView2 构建链，暂不选。Electron 为可替换薄壳，体积/升级成本较高。
- 固定 appId/AUMID `com.philosophersstone.crm`、exe `PhilosopherStoneCRM.exe`、userData `%APPDATA%/PhilosopherStoneCRM`、partition `persist:crm`（首次构建前与 M40 brief 对齐冻结）。程序与数据分离；不读取/搬运/删除 Edge 数据。Web 会话仍可能被服务端撤销或过期。
- 本地设置窗口有最小 IPC，远端 CRM 窗口没有 preload/Node/IPC；两者均 sandbox + contextIsolation。连接只允许严格 SSH 的固定回环 origin 或使用者明确确认的 HTTPS origin。不打包共享凭据。
- OTA 默认未配置禁用，发布源/发布者/证书 pin 由发行构建固定，不允许远端页面或本地表单修改；下载后和安装前都必须严格 Authenticode 验证，拒绝任何未知状态。没有生产证书/托管不宣称生产 OTA 已完成。
- 构建与受控测试在项目内，实际两版 GUI 覆盖升级需专用测试目录和主控协调，不触碰已有 Edge/客户数据。不用静态测试冒充安装验收。

后续构建、使用与验证证据随实现追加。关键选择已通过 TowerSend 请求主控同步 DECISION_LOG（本任务无该文件写权限）。
