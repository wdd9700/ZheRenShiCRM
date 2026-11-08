'use strict';
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const SETTINGS_URL = pathToFileURL(path.join(__dirname, 'settings.html')).href;
const remotePreferences = { sandbox: true, contextIsolation: true, nodeIntegration: false, webSecurity: true, allowRunningInsecureContent: false, webviewTag: false, navigateOnDragDrop: false };
function authorizedSettings(event, window) {
  return !!window && !window.isDestroyed() && event.sender === window.webContents && event.senderFrame === window.webContents.mainFrame && event.senderFrame.url === SETTINGS_URL;
}
function allowedNavigation(value, origin) {
  try { const u = new URL(value); return u.origin === origin && !u.username && !u.password && ['http:', 'https:'].includes(u.protocol); } catch { return false; }
}
function allowedRequest(value, origin) {
  try {
    const u = new URL(value);
    if (['blob:', 'data:'].includes(u.protocol)) return u.protocol === 'data:' || u.origin === origin;
    if (u.protocol === 'ws:') u.protocol = 'http:';
    if (u.protocol === 'wss:') u.protocol = 'https:';
    return u.origin === origin && !u.username && !u.password;
  } catch { return false; }
}
function secureWindow(window, allowed, openSameOrigin = false) {
  const contents = window.webContents;
  contents.setWindowOpenHandler(details => {
    if (openSameOrigin && allowed(details.url)) contents.loadURL(details.url).catch(() => {});
    return { action: 'deny' };
  });
  contents.on('will-attach-webview', event => event.preventDefault());
  for (const name of ['will-navigate', 'will-redirect', 'will-frame-navigate']) {
    contents.on(name, (event, url) => { if (!allowed(url ?? event.url)) event.preventDefault(); });
  }
}
function allowedDownload(contents, item, origin, owned) {
  return !!contents && owned(contents) && allowedNavigation(contents.getURL(), origin) && item.getURLChain().length > 0 && item.getURLChain().every(url => {
    try { const u = new URL(url); return u.protocol === 'blob:' ? u.origin === origin : allowedNavigation(url, origin); } catch { return false; }
  });
}
function secureSession(session, origin, owned, downloads) {
  session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  session.setPermissionCheckHandler(() => false);
  session.removeAllListeners('will-download');
  session.on('will-download', (event, item, contents) => {
    if (!allowedDownload(contents, item, origin, owned)) { event.preventDefault(); return; }
    const filename = path.win32.basename(item.getFilename()).replace(/[<>:"/\\|?*\x00-\x1f]/g, '_') || 'download';
    item.setSaveDialogOptions({ title: '保存 CRM 导出（不会自动打开）', defaultPath: path.join(downloads, filename) });
  });
  session.webRequest.onBeforeRequest((details, callback) => callback({ cancel: !allowedRequest(details.url, origin) }));
}
module.exports = { SETTINGS_URL, remotePreferences, authorizedSettings, allowedNavigation, allowedRequest, allowedDownload, secureWindow, secureSession };
