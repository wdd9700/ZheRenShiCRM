'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const ORIGIN = 'http://127.0.0.1:18088';
const APP_ID = 'com.philosophersstone.crm';
const DATA_DIRECTORY = 'PhilosopherStoneCRM';
const PARTITION = 'persist:crm';
const defaults = () => ({ schemaVersion: 1, connection: { mode: 'external', httpsOrigin: '', trustedHttps: false, host: '', user: '', remotePort: 8088, identityFile: '', knownHostsFile: '' } });
function text(value, max = 512) {
  if (typeof value !== 'string' || value.length > max || /[\x00-\x1f"\r\n]/.test(value)) throw new Error('设置包含无效文本');
  return value;
}
function validateConnection(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('连接设置无效');
  if (!['external', 'ssh', 'https'].includes(input.mode)) throw new Error('连接模式无效');
  const c = defaults().connection;
  c.mode = input.mode;
  for (const key of ['httpsOrigin', 'host', 'user', 'identityFile', 'knownHostsFile']) c[key] = text(input[key] ?? c[key]);
  c.trustedHttps = input.trustedHttps === true;
  c.remotePort = input.remotePort ?? 8088;
  if (!Number.isInteger(c.remotePort) || c.remotePort < 1 || c.remotePort > 65535) throw new Error('远端端口无效');
  if (c.mode === 'https') {
    let url;
    try { url = new URL(c.httpsOrigin); } catch { throw new Error('HTTPS 入口无效'); }
    if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash || !c.trustedHttps) throw new Error('需要明确确认的 HTTPS origin（不含路径/凭据）');
    c.httpsOrigin = url.origin;
  }
  if (c.mode === 'ssh') {
    if (!/^[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$/.test(c.host) || !/^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,63}$/.test(c.user)) throw new Error('SSH 主机或用户格式无效');
    for (const key of ['identityFile', 'knownHostsFile']) {
      if (!path.win32.isAbsolute(c[key]) || c[key].startsWith('\\\\') || c[key].includes('%')) throw new Error('SSH 文件必须是本机绝对路径');
    }
  }
  return c;
}
function migrate(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('配置文件无效，原文件已保留');
  if (raw.schemaVersion !== undefined && raw.schemaVersion !== 0 && raw.schemaVersion !== 1) throw new Error('此客户端不支持较新配置，拒绝覆盖');
  return { ...raw, schemaVersion: 1, connection: { ...raw.connection, ...validateConnection({ ...defaults().connection, ...raw.connection }) } };
}
class SettingsStore {
  constructor(directory) { this.file = path.join(directory, 'settings.json'); this.value = defaults(); }
  load() {
    if (!fs.existsSync(this.file)) return this.value;
    const raw = JSON.parse(fs.readFileSync(this.file, 'utf8'));
    const next = migrate(raw);
    if (raw.schemaVersion !== 1) {
      fs.copyFileSync(this.file, this.file + '.pre-v1', fs.constants.COPYFILE_EXCL);
      this.write(next);
    }
    this.value = next;
    return next;
  }
  write(value) {
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const temporary = this.file + '.' + randomUUID() + '.tmp';
    try { fs.writeFileSync(temporary, JSON.stringify(value, null, 2), { flag: 'wx', mode: 0o600 }); fs.renameSync(temporary, this.file); }
    finally { if (fs.existsSync(temporary)) fs.unlinkSync(temporary); }
    this.value = value;
  }
  save(connection) {
    const validated = validateConnection(connection);
    this.write({ ...this.value, schemaVersion: 1, connection: { ...this.value.connection, ...validated } });
    return this.value;
  }
}
function connectionOrigin(c) { return c.mode === 'https' ? c.httpsOrigin : ORIGIN; }
module.exports = { APP_ID, DATA_DIRECTORY, PARTITION, ORIGIN, defaults, validateConnection, migrate, SettingsStore, connectionOrigin };
