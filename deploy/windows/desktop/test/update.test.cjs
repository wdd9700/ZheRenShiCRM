'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const { validatePolicy, fileHash, parseSignature, verifySignature, verifyInstaller } = require('../src/signature.cjs');
const { trustedUpdateUrl, UpdateController } = require('../src/updater.cjs');
const raw = { enabled: true, feedUrl: 'https://updates.example.invalid/crm/', publisherName: 'CN=Example Publisher, O=Example', certificateSha256: ['A'.repeat(64)] };
const policy = validatePolicy(raw);
const fakeFile = 'C:\\fixture\\installer.exe';
function signature(patch = {}) { return JSON.stringify({ Status: 'Valid', Path: fakeFile, Subject: raw.publisherName, CertificateSha256: 'A'.repeat(64), ...patch }); }
function fixture(t) { fs.mkdirSync(path.join(__dirname, '../.validation'), { recursive: true }); const dir = fs.mkdtempSync(path.join(__dirname, '../.validation/update-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true })); const file = path.join(dir, 'test-x64.exe'); fs.writeFileSync(file, 'unsigned fixture'); return file; }
test('OTA disabled by default, cannot check/download/install', async () => {
  const c = new UpdateController({ enabled: false }); assert.equal(c.status().state, 'disabled');
  for (const action of ['check', 'download', 'install']) await assert.rejects(c[action](), /禁用/);
  for (const patch of [{ publisherName: '' }, { certificateSha256: [] }, { feedUrl: 'http://example.invalid/' }, { feedUrl: 'https://user:pass@example.invalid/' }]) assert.throws(() => validatePolicy({ ...raw, ...patch }));
});
test('OTA feed confines redirects and metadata to HTTPS directory', () => {
  assert.equal(trustedUpdateUrl(raw.feedUrl + 'Setup-1.0.1-x64.exe', policy), true);
  for (const url of ['http://updates.example.invalid/crm/x', 'https://evil.invalid/crm/x', 'https://updates.example.invalid/other/x', raw.feedUrl + '../escape', 'https://user@updates.example.invalid/crm/x']) assert.equal(trustedUpdateUrl(url, policy), false);
});
test('signature accepts only Valid + exact subject, certificate and path', () => {
  assert.equal(parseSignature(signature(), '', fakeFile, policy), true);
  for (const patch of [{ Status: 'NotSigned' }, { Status: 'UnknownError' }, { Status: 'HashMismatch' }, { Subject: 'CN=Wrong' }, { CertificateSha256: 'B'.repeat(64) }, { Path: 'C:\\wrong.exe' }, { Path: null }]) assert.throws(() => parseSignature(signature(patch), '', fakeFile, policy));
  for (const stdout of ['', '{}', 'null', 'malformed', '[]']) assert.throws(() => parseSignature(stdout, '', fakeFile, policy));
  assert.throws(() => parseSignature(signature(), 'warning', fakeFile, policy));
});
test('PowerShell launch/timeout/parse/stderr failures reject and encoded literal cannot inject', async () => {
  for (const [error, out, err] of [[new Error('timeout'), '', ''], [null, 'broken', ''], [null, signature(), 'bad']]) {
    await assert.rejects(verifySignature(fakeFile, policy, (_cmd, args, options, callback) => { assert.equal(options.shell, false); assert.equal(options.timeout, 20000); assert.equal(args[4], '-EncodedCommand'); callback(error, out, err); }, () => 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe'));
  }
  await assert.rejects(verifySignature(fakeFile, policy, () => { throw new Error('spawn blocked'); }, () => { throw new Error('missing PS'); }));
  await verifySignature(fakeFile, policy, (_cmd, _args, _options, cb) => cb(null, signature(), ''), () => 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe');
});
test('real Windows Authenticode rejects unsigned EXE fixture', { skip: process.platform !== 'win32' }, async t => {
  const file = fixture(t); await assert.rejects(verifySignature(file, policy), /签名|验签/);
});
test('hash mismatch, truncated file and post-verification replacement reject', async t => {
  const file = fixture(t); const digest = await fileHash(file);
  await assert.rejects(verifyInstaller(file, policy, 'B'.repeat(86) + '==', async () => {}), /SHA512/);
  await assert.rejects(verifyInstaller(file, policy, digest, async () => fs.appendFileSync(file, 'replacement')), /发生变化/);
  fs.writeFileSync(file, 'x'); await assert.rejects(verifyInstaller(file, policy, digest, async () => {}), /SHA512/);
});
async function controller(t, overrides = {}) {
  const file = fixture(t); const digest = await fileHash(file); const updater = new EventEmitter();
  updater.currentVersion = { version: '1.0.0' }; updater.installerPath = file; updater.checkForUpdates = async () => ({ updateInfo: { version: '1.0.1', files: [{ url: 'Setup-1.0.1-x64.exe', sha512: digest, size: fs.statSync(file).size }] } });
  updater.downloadUpdate = async () => [file]; updater.quitAndInstall = () => { updater.installed = true; };
  let calls = 0;
  const c = new UpdateController(raw, { factory: () => updater, confirm: async () => true, flush: async () => {}, verifier: async (...args) => { calls++; return verifyInstaller(...args, async () => {}); }, ...overrides });
  return { c, updater, file, calls: () => calls };
}
test('controlled two-stage verification and explicit install succeeds only after user confirms', async t => {
  const { c, updater, calls } = await controller(t);
  assert.equal((await c.check()).state, 'available'); assert.equal((await c.download()).state, 'ready'); assert.equal(calls(), 1);
  await c.install(); assert.equal(calls(), 2); assert.equal(updater.installed, true);
});
test('user cancel never downloads or installs', async t => {
  const { c, updater } = await controller(t, { confirm: async () => false }); await c.check(); await c.download(); assert.equal(c.status().state, 'available'); assert.equal(updater.installed, undefined);
});
test('cache replaced after download refuses installation and retains old program', async t => {
  const { c, updater, file } = await controller(t); await c.check(); await c.download(); fs.writeFileSync(file, 'replaced');
  await assert.rejects(c.install(), /SHA512/); assert.equal(updater.installed, undefined); assert.equal(c.status().state, 'failed');
});
test('signature failure, flush failure, and changed cache path fail closed', async t => {
  const bad = await controller(t, { verifier: async () => { throw new Error('signature rejected'); } }); await bad.c.check(); await assert.rejects(bad.c.download(), /signature/); assert.equal(bad.updater.installed, undefined);
  const flush = await controller(t, { flush: async () => { throw new Error('disk full'); } }); await flush.c.check(); await flush.c.download(); await assert.rejects(flush.c.install(), /disk full/); assert.equal(flush.updater.installed, undefined);
  const changed = await controller(t); await changed.c.check(); await changed.c.download(); changed.updater.installerPath = 'wrong.exe'; await assert.rejects(changed.c.install(), /缓存路径/); assert.equal(changed.updater.installed, undefined);
});
test('untrusted metadata, downgrade and broken TLS remain on old version', async t => {
  const { c, updater } = await controller(t);
  updater.checkForUpdates = async () => ({ updateInfo: { version: '0.9.9' } }); assert.equal((await c.check()).state, 'current');
  updater.checkForUpdates = async () => ({ updateInfo: { version: '1.0.1', files: [{ url: 'https://evil.invalid/x.exe', sha512: 'A'.repeat(86) + '==', size: 1 }] } }); await assert.rejects(c.check(), /URL/);
  updater.checkForUpdates = async () => { throw new Error('certificate invalid'); }; await assert.rejects(c.check(), /certificate/); assert.equal(updater.installed, undefined);
});
