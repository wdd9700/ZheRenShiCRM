'use strict';
const { app, BrowserWindow, session, ipcMain, dialog } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { createHash } = require('node:crypto');
const { APP_ID, DATA_DIRECTORY, PARTITION, SettingsStore, defaults } = require('./settings.cjs');
const { remotePreferences, secureWindow, secureSession, allowedNavigation } = require('./security.cjs');
if (APP_ID !== 'com.philosophersstone.crm.acceptance' || DATA_DIRECTORY !== 'PhilosopherStoneCRM-Acceptance') throw new Error('验收入口不能用于生产身份');
const data = path.join(app.getPath('appData'), DATA_DIRECTORY);
const marker = path.join(data, 'acceptance-only.marker');
if (fs.existsSync(data) && fs.readdirSync(data).length && !fs.existsSync(marker)) throw new Error('未知验收目录，拒绝覆盖');
fs.mkdirSync(data, { recursive: true });
fs.writeFileSync(marker, 'synthetic-only-W020');
require('./main.cjs');
const origin = 'http://127.0.0.1:28189';
const csv = Buffer.from('\uFEFF姓名,结果\r\n合成验收,保留升级哨兵\r\n', 'utf8');
let window;
let server;
let downloads = [];
app.whenReady().then(async () => {
  server = http.createServer((request, response) => {
    if (request.headers.host !== '127.0.0.1:28189') { response.writeHead(403).end(); return; }
    const headers = { 'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-src 'none'", 'X-Content-Type-Options': 'nosniff' };
    if (request.url === '/') { response.writeHead(200, { ...headers, 'Content-Type': 'text/html; charset=utf-8' }); response.end(fs.readFileSync(path.join(__dirname, 'fixture.html'))); }
    else if (request.url === '/fixture.js') { response.writeHead(200, { ...headers, 'Content-Type': 'text/javascript; charset=utf-8' }); response.end(fs.readFileSync(path.join(__dirname, 'fixture.js'))); }
    else if (request.url === '/download') { response.writeHead(200, { 'Content-Type': 'text/csv; charset=utf-8', 'Content-Disposition': "attachment; filename*=UTF-8''%E5%90%88%E6%88%90%E9%AA%8C%E6%94%B6.csv" }); response.end(csv); }
    else { response.writeHead(404).end(); }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(28189, '127.0.0.1', resolve); });
  const s = session.fromPartition(PARTITION);
  const downloadDir = path.join(data, 'fixture-downloads'); fs.mkdirSync(downloadDir, { recursive: true });
  secureSession(s, origin, contents => window && contents === window.webContents, downloadDir);
  s.on('will-download', (_event, item) => {
    item.setSavePath(path.join(downloadDir, '合成验收.csv'));
    item.once('done', (_event, state) => {
      if (state !== 'completed') return;
      const file = path.join(downloadDir, '合成验收.csv'); const bytes = fs.readFileSync(file);
      if (bytes.equals(csv)) downloads.push({ name: '合成验收.csv', sha256: createHash('sha256').update(bytes).digest('hex') });
    });
  });
  window = new BrowserWindow({ width: 950, height: 800, title: 'W020 验收专用（非生产客户端）', webPreferences: { ...remotePreferences, session: s, preload: path.join(__dirname, 'acceptance-preload.cjs') } });
  secureWindow(window, url => allowedNavigation(url, origin), true);
  function authorize(event) { if (event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame || event.senderFrame.url !== origin + '/') throw new Error('拒绝验收 IPC'); }
  ipcMain.handle('acceptance:seed', async event => {
    authorize(event);
    const store = new SettingsStore(data); store.load(); store.save({ ...defaults().connection, host: 'synthetic-upgrade-sentinel.invalid' });
    await s.cookies.set({ url: origin, name: 'w020_synthetic', value: 'persistent-cookie-sentinel', expirationDate: Date.now() / 1000 + 86400 * 30, httpOnly: true, sameSite: 'lax' });
    return { version: app.getVersion(), profile: data, partition: PARTITION };
  });
  ipcMain.handle('acceptance:report', async (event, snapshot) => {
    authorize(event);
    if (snapshot?.localStorage !== 'W020-localStorage-中文' || snapshot?.indexedDB !== 'W020-indexedDB-中文' || snapshot.node !== false) throw new Error('浏览器存储或安全哨兵不符');
    const store = new SettingsStore(data); store.load();
    if (store.value.connection.host !== 'synthetic-upgrade-sentinel.invalid') throw new Error('设置哨兵缺失');
    const cookie = (await s.cookies.get({ url: origin, name: 'w020_synthetic' }))[0];
    if (cookie?.value !== 'persistent-cookie-sentinel' || !cookie.httpOnly) throw new Error('持久 Cookie 哨兵缺失');
    const file = path.join(downloadDir, '合成验收.csv');
    if (!fs.existsSync(file) || !fs.readFileSync(file).equals(csv)) throw new Error('下载哨兵缺失或变化');
    await s.cookies.flushStore(); await s.flushStorageData();
    const receipt = { version: app.getVersion(), appId: APP_ID, partition: PARTITION, profile: data, settingsSha256: createHash('sha256').update(fs.readFileSync(store.file)).digest('hex'), localStorage: snapshot.localStorage, indexedDB: snapshot.indexedDB, cookiePreserved: true, nodeUnavailable: true, downloadSha256: createHash('sha256').update(csv).digest('hex'), downloadsThisRun: downloads.length };
    const target = path.join(data, 'receipt-' + app.getVersion() + '.json'); fs.writeFileSync(target, JSON.stringify(receipt, null, 2)); return receipt;
  });
  await window.loadURL(origin + '/');
}).catch(error => { dialog.showErrorBox('验收夹具失败', error.message); app.quit(); });
app.on('will-quit', () => server?.close());
