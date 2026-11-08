'use strict';
const { app, BrowserWindow, session, ipcMain, dialog, Menu, shell } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { APP_ID, DATA_DIRECTORY, PARTITION, SettingsStore, connectionOrigin } = require('./settings.cjs');
const { SETTINGS_URL, remotePreferences, authorizedSettings, allowedNavigation, secureWindow, secureSession } = require('./security.cjs');
const { Tunnel } = require('./tunnel.cjs');
const { UpdateController, createUpdateController, loadPolicy } = require('./updater.cjs');
app.setAppUserModelId(APP_ID);
const data = path.join(app.getPath('appData'), DATA_DIRECTORY);
fs.mkdirSync(path.join(data, 'browser'), { recursive: true });
app.setPath('userData', data);
app.setPath('sessionData', path.join(data, 'browser'));
let settingsWindow;
let crmWindow;
let crmSession;
let store;
let updates;
let connecting = false;
let shuttingDown = false;
const tunnel = new Tunnel(() => {
  if (crmWindow && !crmWindow.isDestroyed()) crmWindow.close();
  if (!shuttingDown) dialog.showErrorBox('SSH 隧道已关闭', '请检查网络、个人公钥及 known_hosts 后重新连接。客户端不会自动换端口或结束其他进程。');
});
function showSettings() {
  if (settingsWindow && !settingsWindow.isDestroyed()) { settingsWindow.show(); settingsWindow.focus(); return; }
  settingsWindow = new BrowserWindow({ width: 900, height: 900, title: '哲人石CRM · 连接设置', webPreferences: { ...remotePreferences, preload: path.join(__dirname, 'preload.cjs'), partition: 'settings-ui' } });
  secureWindow(settingsWindow, url => url === SETTINGS_URL);
  settingsWindow.webContents.session.setPermissionRequestHandler((_w, _p, callback) => callback(false));
  settingsWindow.webContents.session.setPermissionCheckHandler(() => false);
  settingsWindow.loadURL(SETTINGS_URL).catch(() => dialog.showErrorBox('无法加载设置', '请重新安装完整客户端，用户数据不会被删除。'));
}
async function flush() {
  if (crmSession) { await crmSession.cookies.flushStore(); await crmSession.flushStorageData(); }
  if (store && fs.existsSync(store.file)) {
    const backup = path.join(data, `settings.pre-update-${Date.now()}.json`);
    fs.copyFileSync(store.file, backup, fs.constants.COPYFILE_EXCL);
  }
}
async function confirmUpdate(kind, version) {
  const result = await dialog.showMessageBox(settingsWindow, { type: 'question', buttons: ['取消', kind === 'install' ? '已保存，安装并重启' : '下载'], defaultId: 0, cancelId: 0, title: '哲人石CRM 客户端更新', message: kind === 'install' ? `安装 ${version} 并重启？请先保存所有 CRM 表单。` : `下载客户端 ${version}？`, detail: (updates?.policy?.trust === 'pinned-key-ed25519' ? '使用客户端固定 Ed25519 公钥验证发行清单和安装包；这不是 Windows 发布者认证，仍可能显示未知发布者。' : '仅接受发行策略指定证书的有效 Windows 签名。') + ' 安装前会再次检查文件；保留客户端数据不代表会话永不过期。' });
  return result.response === 1;
}
async function connect() {
  if (connecting) throw new Error('正在连接');
  if (crmWindow && !crmWindow.isDestroyed()) { crmWindow.show(); crmWindow.focus(); return; }
  connecting = true;
  try {
    const c = store.value.connection;
    const origin = connectionOrigin(c);
    if (c.mode === 'ssh' && !tunnel.child) await tunnel.start(c);
    if (c.mode === 'external') {
      const result = await dialog.showMessageBox(settingsWindow, { type: 'warning', buttons: ['取消', '我已核验，连接'], defaultId: 0, cancelId: 0, message: '确认 127.0.0.1:18088 是你自行建立的受信 SSH 隧道？', detail: '本机监听者不等于服务端身份。本模式不会替你验证外部隧道，也不会管理或结束它。' });
      if (result.response !== 1) return;
    }
    crmSession = session.fromPartition(PARTITION);
    secureSession(crmSession, origin, contents => !!crmWindow && !crmWindow.isDestroyed() && contents === crmWindow.webContents, app.getPath('downloads'));
    const response = await crmSession.fetch(origin + '/api/method/ping', { redirect: 'error', credentials: 'omit', signal: AbortSignal.timeout(15000) });
    if (!response.ok || (await response.json()).message !== 'pong') throw new Error('CRM 健康检查未通过');
    const login = await crmSession.fetch(origin + '/login', { redirect: 'error', credentials: 'omit', signal: AbortSignal.timeout(15000) });
    if (!login.ok || !login.headers.get('content-type')?.includes('text/html')) throw new Error('CRM 登录页不可用');
    crmWindow = new BrowserWindow({ width: 1280, height: 850, title: '哲人石CRM', webPreferences: { ...remotePreferences, session: crmSession } });
    let externalPending = false;
    secureWindow(crmWindow, url => allowedNavigation(url, origin), true, async url => {
      if (externalPending || !crmWindow || crmWindow.isDestroyed()) return;
      externalPending = true;
      try {
        const result = await dialog.showMessageBox(crmWindow, { type: 'question', buttons: ['取消', '在系统浏览器打开'], defaultId: 0, cancelId: 0, message: '离开 CRM 打开外部网站？', detail: url + '\n该网站不属于 CRM 受信入口；不要向不可信网站提供账号或资料。' });
        if (result.response === 1) await shell.openExternal(url, { activate: true });
      } finally { externalPending = false; }
    });
    crmWindow.webContents.on('page-title-updated', event => { event.preventDefault(); crmWindow.setTitle('哲人石CRM'); });
    crmWindow.on('closed', () => { crmWindow = null; });
    await crmWindow.loadURL(origin + '/login?redirect-to=/crm');
  } catch (e) {
    if (crmWindow && !crmWindow.isDestroyed()) crmWindow.close();
    throw new Error('连接失败：' + e.message);
  } finally { connecting = false; }
}
function handle(channel, fn) {
  ipcMain.handle(channel, async (event, ...args) => {
    if (!authorizedSettings(event, settingsWindow)) throw new Error('拒绝非本地设置主页面请求');
    return fn(...args);
  });
}
if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', showSettings);
  app.on('activate', showSettings);
  app.whenReady().then(() => {
    store = new SettingsStore(data);
    try { store.load(); } catch { dialog.showErrorBox('配置无法读取', '原配置文件已保留，拒绝覆盖；请联系管理员备份并检查 settings.json。'); app.quit(); return; }
    try {
      const resources = app.isPackaged ? process.resourcesPath : path.join(__dirname, '..', 'release');
      const { readConnectionPolicy, initializeConnection } = require('./connection-policy.cjs');
      initializeConnection(store, readConnectionPolicy(resources));
      updates = createUpdateController(loadPolicy(resources), { confirm: confirmUpdate, flush, dataDirectory: data, currentVersion: app.getVersion() });
      if (store.value.connection.mode === 'https' && store.value.connection.trustedHttps) setImmediate(() => connect().catch(() => { showSettings(); dialog.showErrorBox('连接未就绪', '请检查服务端可信 HTTPS 入口；不会降级 HTTP 或忽略证书错误。'); }));
    }
    catch { dialog.showErrorBox('发行配置无效', '拒绝启用更新或新入口配置；原数据已保留，请联系发行管理员。'); updates = new UpdateController({ enabled: false }); }
    handle('settings:read', () => ({ connection: store.value.connection, version: app.getVersion() }));
    handle('settings:save', connection => {
      if (crmWindow || tunnel.child || connecting) throw new Error('请关闭 CRM 并退出客户端后再修改连接；不会终止未知进程');
      return { connection: store.save(connection).connection };
    });
    handle('connection:open', connect);
    handle('update:status', () => updates.status());
    handle('update:check', () => updates.check());
    handle('update:download', () => updates.download());
    handle('update:install', () => updates.install());
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      { label: '哲人石CRM', submenu: [{ label: '连接设置 / 客户端更新', click: showSettings }, { role: 'quit', label: '退出' }] },
      { label: '编辑', submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] },
      { label: '视图', submenu: [{ role: 'reload', label: '重新加载' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }] }
    ]));
    showSettings();
  }).catch(() => { dialog.showErrorBox('启动失败', '客户端无法启动；用户数据已保留，请联系管理员。'); app.quit(); });
}
app.on('window-all-closed', () => app.quit());
app.on('before-quit', event => {
  if (shuttingDown) return;
  event.preventDefault();
  shuttingDown = true;
  tunnel.stop();
  flush().then(() => app.quit(), () => { shuttingDown = false; dialog.showErrorBox('无法保存客户端状态', '退出已取消，请检查磁盘空间并重试。'); showSettings(); });
});
