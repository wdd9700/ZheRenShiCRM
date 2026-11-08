'use strict';
const form = document.querySelector('#connection');
const status = document.querySelector('#status');
const updateState = document.querySelector('#update-state');
async function action(fn) { try { status.textContent = ''; return await fn(); } catch (error) { status.textContent = error.message; } }
async function refresh() {
  const state = await window.desktop.updateStatus();
  updateState.textContent = state.state === 'disabled' ? 'OTA 未配置，已禁用。当前安装包未签名，不代表生产 OTA 已可用。' : `更新状态：${state.state}${state.version ? ' · ' + state.version : ''}`;
  document.querySelector('#check').disabled = state.state === 'disabled';
  document.querySelector('#download').disabled = state.state !== 'available';
  document.querySelector('#install').disabled = state.state !== 'ready';
}
action(async () => {
  const value = await window.desktop.readSettings();
  for (const [key, item] of Object.entries(value.connection)) { const el = form.elements.namedItem(key); if (el) { if (el.type === 'checkbox') el.checked = item; else el.value = item; } }
  document.title = `哲人石CRM ${value.version} · 连接设置`;
  await refresh();
});
form.addEventListener('submit', event => { event.preventDefault(); action(async () => {
  const c = Object.fromEntries(new FormData(form)); c.remotePort = Number(c.remotePort); c.trustedHttps = form.elements.trustedHttps.checked;
  await window.desktop.saveSettings(c); status.textContent = '设置已保存；打开 CRM 后生效。';
}); });
document.querySelector('#open').onclick = () => action(() => window.desktop.connect());
for (const [id, method] of [['check', 'checkUpdate'], ['download', 'downloadUpdate'], ['install', 'installUpdate']]) document.querySelector('#' + id).onclick = () => action(async () => { try { await window.desktop[method](); } finally { await refresh(); } });
