'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { SettingsStore, defaults, migrate, validateConnection, APP_ID, DATA_DIRECTORY, PARTITION } = require('../src/settings.cjs');
const { SETTINGS_URL, authorizedSettings, allowedNavigation, allowedRequest, allowedDownload, remotePreferences } = require('../src/security.cjs');
const { sshArguments, portFree } = require('../src/tunnel.cjs');
function fixture(t) { const directory = fs.mkdtempSync(path.join(__dirname, '../.validation/core-')); t.after(() => fs.rmSync(directory, { recursive: true, force: true })); return directory; }
fs.mkdirSync(path.join(__dirname, '../.validation'), { recursive: true });
test('fixed identity and browser isolation contract', () => {
  assert.equal(APP_ID, 'com.philosophersstone.crm'); assert.equal(DATA_DIRECTORY, 'PhilosopherStoneCRM'); assert.equal(PARTITION, 'persist:crm');
  assert.deepEqual([remotePreferences.sandbox, remotePreferences.contextIsolation, remotePreferences.nodeIntegration, remotePreferences.webSecurity, remotePreferences.webviewTag], [true, true, false, true, false]);
  assert.equal(remotePreferences.preload, undefined);
});
test('settings two-version reopen retains unknown fields and browser data', t => {
  const directory = fixture(t); const store = new SettingsStore(directory);
  store.write({ ...defaults(), retained: { marker: '中文合成' }, connection: { ...defaults().connection, futureOption: 'keep' } });
  fs.mkdirSync(path.join(directory, 'browser')); fs.writeFileSync(path.join(directory, 'browser', 'sentinel'), 'do not delete');
  const next = new SettingsStore(directory); next.load(); next.save({ ...next.value.connection, host: 'crm.example.invalid' });
  const reopened = new SettingsStore(directory); const value = reopened.load();
  assert.equal(value.retained.marker, '中文合成'); assert.equal(value.connection.futureOption, 'keep');
  assert.equal(fs.readFileSync(path.join(directory, 'browser', 'sentinel'), 'utf8'), 'do not delete');
});
test('migration backs up exact prior bytes and does not destroy future/corrupt schemas', t => {
  const directory = fixture(t); const file = path.join(directory, 'settings.json');
  const original = JSON.stringify({ schemaVersion: 0, custom: 'keep', connection: defaults().connection }); fs.writeFileSync(file, original);
  assert.equal(new SettingsStore(directory).load().custom, 'keep'); assert.equal(fs.readFileSync(file + '.pre-v1', 'utf8'), original);
  const future = '{"schemaVersion":99}'; fs.writeFileSync(file, future); assert.throws(() => new SettingsStore(directory).load()); assert.equal(fs.readFileSync(file, 'utf8'), future);
  fs.writeFileSync(file, 'broken'); assert.throws(() => new SettingsStore(directory).load()); assert.equal(fs.readFileSync(file, 'utf8'), 'broken');
  assert.throws(() => migrate([]));
});
test('connection rejects injected host/user/path and unconfirmed HTTPS', () => {
  const c = { ...defaults().connection, mode: 'ssh', host: 'example.invalid', user: 'person', identityFile: 'C:\\Users\\person\\key file', knownHostsFile: 'C:\\Users\\person\\known hosts' };
  assert.equal(validateConnection(c).host, 'example.invalid');
  for (const patch of [{ host: '-oProxyCommand=calc' }, { user: 'a@evil' }, { remotePort: 0 }, { identityFile: '\\\\server\\share\\key' }, { knownHostsFile: 'relative' }, { identityFile: 'C:\\key" -o x' }]) assert.throws(() => validateConnection({ ...c, ...patch }));
  for (const httpsOrigin of ['http://evil.invalid', 'https://user:pass@evil.invalid', 'https://evil.invalid/path', 'https://evil.invalid/?x']) assert.throws(() => validateConnection({ ...c, mode: 'https', trustedHttps: true, httpsOrigin }));
  assert.throws(() => validateConnection({ ...c, mode: 'https', httpsOrigin: 'https://crm.example.invalid' }));
  assert.equal(validateConnection({ ...c, mode: 'https', trustedHttps: true, httpsOrigin: 'https://crm.example.invalid' }).httpsOrigin, 'https://crm.example.invalid');
});
test('IPC rejects remote, wrong window, subframe, and URL variants', () => {
  const frame = { url: SETTINGS_URL }; const contents = { mainFrame: frame }; const window = { isDestroyed: () => false, webContents: contents };
  assert.equal(authorizedSettings({ sender: contents, senderFrame: frame }, window), true);
  assert.equal(authorizedSettings({ sender: {}, senderFrame: frame }, window), false);
  assert.equal(authorizedSettings({ sender: contents, senderFrame: { url: SETTINGS_URL } }, window), false);
  frame.url = SETTINGS_URL + '?remote'; assert.equal(authorizedSettings({ sender: contents, senderFrame: frame }, window), false);
  frame.url = 'https://crm.example.invalid'; assert.equal(authorizedSettings({ sender: contents, senderFrame: frame }, window), false);
});
test('origin redirects, requests, downloads and websocket confinement', () => {
  const origin = 'http://127.0.0.1:18088';
  for (const url of [origin + '/crm', origin + '/login']) assert.equal(allowedNavigation(url, origin), true);
  for (const url of ['http://127.0.0.1:8088', 'http://localhost:18088', 'https://evil.invalid', 'file:///C:/file', 'javascript:alert(1)', 'data:text/html,x', origin + '@evil.invalid']) assert.equal(allowedNavigation(url, origin), false);
  assert.equal(allowedRequest('ws://127.0.0.1:18088/socket.io', origin), true);
  assert.equal(allowedRequest('blob:' + origin + '/uuid', origin), true);
  assert.equal(allowedRequest('blob:https://evil.invalid/uuid', origin), false);
  const contents = { getURL: () => origin + '/resource-import' };
  const item = { getURLChain: () => ['blob:' + origin + '/uuid'] };
  assert.equal(allowedDownload(contents, item, origin, w => w === contents), true);
  assert.equal(allowedDownload(contents, item, origin, () => false), false);
  assert.equal(allowedDownload(contents, { getURLChain: () => ['https://evil.invalid/download'] }, origin, () => true), false);
});
test('SSH is strict, public-key only, fixed origin and never uses shell', () => {
  const args = sshArguments({ ...defaults().connection, mode: 'ssh', host: 'example.invalid', user: 'person', identityFile: 'C:\\key file', knownHostsFile: 'C:\\known hosts' });
  for (const arg of ['NUL', 'StrictHostKeyChecking=yes', 'BatchMode=yes', 'IdentitiesOnly=yes', 'IdentityAgent=none', 'GlobalKnownHostsFile=NUL', 'ExitOnForwardFailure=yes', '127.0.0.1:18088:127.0.0.1:8088', 'UserKnownHostsFile="C:\\known hosts"']) assert.ok(args.includes(arg));
});
test('busy fixed port fails without selecting another port', async t => {
  const net = require('node:net'); const server = net.createServer();
  const ownsListener = await new Promise((resolve, reject) => {
    server.once('error', error => error.code === 'EADDRINUSE' ? resolve(false) : reject(error));
    server.listen(18088, '127.0.0.1', () => resolve(true));
  });
  if (ownsListener) t.after(() => server.close());
  await assert.rejects(portFree(), /18088/);
});
