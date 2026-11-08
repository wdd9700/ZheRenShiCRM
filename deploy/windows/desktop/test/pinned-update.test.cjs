'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const { generateKeyPairSync, sign, randomUUID } = require('node:crypto');
const { spawnSync } = require('node:child_process');
const { validatePolicy } = require('../src/signature.cjs');
const { FORMAT, sha256, verifyManifest, authorizeRelease, ReleaseState, verifyBoundInstallerSync } = require('../src/signed-manifest.cjs');
const { PinnedUpdateController, createPinnedInstaller } = require('../src/pinned-updater.cjs');
const { createUpdateController, buildUpdateConfig } = require('../src/updater.cjs');
const { responseFor, trustedUrl, limiter } = require('../src/ota-transport.cjs');
const { keyId, signRelease } = require('../scripts/release-tools.cjs');
const root = path.resolve(__dirname, '..');
const pair = generateKeyPairSync('ed25519');
const rawPolicy = { enabled: true, trust: 'pinned-key-ed25519', feedUrl: 'https://updates.example.invalid/crm/', publicKey: pair.publicKey.export({ type: 'spki', format: 'pem' }).toString(), keyId: keyId(pair.publicKey), minSequence: 1 };
const policy = validatePolicy(rawPolicy);
const payload = Buffer.from('synthetic installer bytes, never executed');
function signed(patch = {}, key = pair.privateKey) {
  const manifest = { format: FORMAT, keyId: rawPolicy.keyId, version: '1.0.1', sequence: 1, platform: 'win32', arch: 'x64', file: 'PhilosopherStoneCRM-Setup-1.0.1-x64.exe', size: payload.length, sha256: sha256(payload), ...patch };
  const bytes = Buffer.from(JSON.stringify(manifest) + '\n'); return { bytes, signature: sign(null, bytes, key) };
}
function directory(t) { fs.mkdirSync(path.join(root, '.validation'), { recursive: true }); const dir = fs.mkdtempSync(path.join(root, '.validation/pinned-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true })); return dir; }
function fixture(t, release = signed(), overrides = {}) {
  const dir = directory(t); const installer = new EventEmitter(); installer.prepareVerified = async value => { installer.receipt = value; }; installer.quitAndInstall = () => { installer.invoked = true; };
  const network = { fetchBytes: async url => { if (url.endsWith('manifest.json')) return release.bytes; if (url.endsWith('manifest.sig')) return release.signature; throw new Error('unexpected URL'); }, downloadFile: async (url, _policy, file) => { assert.ok(url.endsWith('PhilosopherStoneCRM-Setup-1.0.1-x64.exe')); fs.writeFileSync(file, payload, { flag: 'wx' }); } };
  const controller = new PinnedUpdateController(policy, { dataDirectory: dir, currentVersion: '1.0.0', confirm: async () => true, flush: async () => {}, installerFactory: () => installer, network, ...overrides });
  return { dir, controller, installer, network };
}
test('Ed25519 raw bytes verify before any JSON fields are trusted', () => {
  const value = signed(); assert.equal(verifyManifest(value.bytes, value.signature, policy).manifest.version, '1.0.1');
  for (const bytes of [Buffer.concat([value.bytes, Buffer.from(' ')]), Buffer.from(value.bytes.toString().replace('1.0.1', '9.9.9')), Buffer.from('not json')]) assert.throws(() => verifyManifest(bytes, value.signature, policy), /签名/);
  assert.throws(() => verifyManifest(value.bytes, value.signature.subarray(0, 63), policy), /长度/);
  const other = generateKeyPairSync('ed25519'); assert.throws(() => verifyManifest(value.bytes, sign(null, value.bytes, other.privateKey), policy), /不可信/);
  const unknown = signed({ keyId: 'server-proposed-key' }); assert.throws(() => verifyManifest(unknown.bytes, unknown.signature, policy), /keyId/);
});
test('trusted signer still must bind strict architecture, filename, size, schema and stable version', () => {
  for (const patch of [{ platform: 'linux' }, { arch: 'arm64' }, { file: '../payload.exe' }, { file: 'https://evil.invalid/payload.exe' }, { size: 0 }, { size: 900000000 }, { sha256: 'bad' }, { sequence: 0 }, { version: '1.0.2-beta' }, { extra: 'field' }]) { const value = signed(patch); assert.throws(() => verifyManifest(value.bytes, value.signature, policy)); }
  assert.throws(() => validatePolicy({ ...rawPolicy, trust: 'none' }));
  assert.throws(() => validatePolicy({ ...rawPolicy, publicKey: generateKeyPairSync('rsa', { modulusLength: 2048 }).publicKey.export({ type: 'spki', format: 'pem' }).toString() }));
  assert.deepEqual(buildUpdateConfig(rawPolicy), { updaterCacheDirName: 'philosopher-stone-crm-updater' });
});
test('high-water rejects rollback, same-sequence substitution and installed-version downgrade', t => {
  const store = new ReleaseState(directory(t)); const value = signed(); const release = verifyManifest(value.bytes, value.signature, policy);
  store.accept(release, policy, '1.0.0'); store.accept(release, policy, '1.0.0');
  const replacement = signed({ sha256: 'a'.repeat(64) }); assert.throws(() => authorizeRelease(verifyManifest(replacement.bytes, replacement.signature, policy), policy, '1.0.0', store.load()), /同序号/);
  const rollback = signed({ sequence: 2 }); assert.throws(() => authorizeRelease(verifyManifest(rollback.bytes, rollback.signature, policy), policy, '1.0.2', store.load()), /回退/);
  assert.throws(() => authorizeRelease(release, { ...policy, minSequence: 2 }, '1.0.0', null), /回退/);
  fs.writeFileSync(store.file, 'broken'); assert.throws(() => store.load()); assert.equal(fs.readFileSync(store.file, 'utf8'), 'broken');
});
test('legitimate check-download-install chain verifies signed package and commits high-water only after full download', async t => {
  const { controller, installer } = fixture(t);
  assert.equal((await controller.check()).state, 'available'); assert.equal(controller.stateStore.load(), null);
  assert.equal((await controller.download()).state, 'ready'); assert.equal(controller.stateStore.load().sequence, 1);
  assert.equal((await controller.install()).state, 'installing'); assert.equal(installer.invoked, true);
});
test('tampered manifest prevents package download and creates no high-water', async t => {
  const release = signed(); release.bytes = Buffer.from(release.bytes.toString().replace('1.0.1', '9.0.0'));
  const { controller, installer } = fixture(t, release); await assert.rejects(controller.check(), /签名/); assert.equal(controller.stateStore.load(), null); assert.equal(installer.invoked, undefined);
});
test('network failure and bad package never poison high-water or block legitimate retry', async t => {
  const { controller, network } = fixture(t); await controller.check(); const goodDownload = network.downloadFile;
  network.downloadFile = async (_url, _policy, file) => { fs.writeFileSync(file, 'half'); throw new Error('network failed'); };
  await assert.rejects(controller.download(), /network/); assert.equal(controller.stateStore.load(), null);
  await controller.check(); network.downloadFile = async (_url, _policy, file) => fs.writeFileSync(file, Buffer.alloc(payload.length));
  await assert.rejects(controller.download(), /SHA256/); assert.equal(controller.stateStore.load(), null);
  await controller.check(); network.downloadFile = goodDownload; assert.equal((await controller.download()).state, 'ready');
});
test('post-download package substitution, signature replacement, flush failure and cancellation never install', async t => {
  const a = fixture(t); await a.controller.check(); await a.controller.download(); fs.writeFileSync(a.installer.receipt.file, Buffer.alloc(payload.length)); await assert.rejects(a.controller.install(), /SHA256/); assert.equal(a.installer.invoked, undefined);
  const b = fixture(t); await b.controller.check(); await b.controller.download(); b.controller.receipt.signature = Buffer.alloc(64); await assert.rejects(b.controller.install(), /签名/); assert.equal(b.installer.invoked, undefined);
  const c = fixture(t, signed(), { flush: async () => { throw new Error('disk full'); } }); await c.controller.check(); await c.controller.download(); await assert.rejects(c.controller.install(), /disk/); assert.equal(c.installer.invoked, undefined);
  const d = fixture(t, signed(), { confirm: async () => false }); await d.controller.check(); assert.equal((await d.controller.download()).state, 'available'); assert.equal(d.controller.stateStore.load(), null);
});
test('damaged ordinary cache recovers same signed sequence in the same instance and after restart', async t => {
  for (const restart of [false, true]) {
    const { dir, controller, installer, network } = fixture(t);
    let downloads = 0; const originalDownload = network.downloadFile;
    network.downloadFile = async (...args) => { downloads++; return originalDownload(...args); };
    await controller.check(); await controller.download();
    const file = installer.receipt.file;
    const highWater = fs.readFileSync(controller.stateStore.file);
    fs.writeFileSync(file, restart ? 'truncated' : Buffer.alloc(payload.length));
    await assert.rejects(controller.install(), /大小|SHA256/); assert.equal(installer.invoked, undefined);
    let retry = controller;
    const retryInstaller = new EventEmitter(); retryInstaller.prepareVerified = async value => { retryInstaller.receipt = value; }; retryInstaller.quitAndInstall = () => { retryInstaller.invoked = true; };
    if (restart) retry = new PinnedUpdateController(policy, { dataDirectory: dir, currentVersion: '1.0.0', confirm: async () => true, flush: async () => {}, installerFactory: () => retryInstaller, network });
    assert.equal((await retry.check()).state, 'available'); assert.equal((await retry.download()).state, 'ready');
    assert.equal(downloads, 2); assert.deepEqual(fs.readFileSync(file), payload); assert.deepEqual(fs.readFileSync(retry.stateStore.file), highWater);
    await retry.check(); await retry.download(); assert.equal(downloads, 2, 'valid cache must remain reusable');
    await retry.install(); assert.equal((restart ? retryInstaller : installer).invoked, true);
  }
});
test('failed replacement preserves damaged ordinary cache and high-water until a fully verified retry', async t => {
  const { controller, installer, network } = fixture(t); await controller.check(); await controller.download();
  const file = installer.receipt.file; const damaged = Buffer.alloc(payload.length); fs.writeFileSync(file, damaged);
  const highWater = fs.readFileSync(controller.stateStore.file); const originalDownload = network.downloadFile;
  for (const fail of ['network', 'hash']) {
    network.downloadFile = async (_url, _policy, temporary) => { fs.writeFileSync(temporary, Buffer.alloc(payload.length)); if (fail === 'network') throw new Error('network interrupted'); };
    await controller.check(); await assert.rejects(controller.download(), /network|SHA256/);
    assert.deepEqual(fs.readFileSync(file), damaged); assert.deepEqual(fs.readFileSync(controller.stateStore.file), highWater);
    assert.equal(installer.invoked, undefined); assert.equal(fs.readdirSync(controller.cacheDirectory).length, 1);
  }
  network.downloadFile = originalDownload; await controller.check(); assert.equal((await controller.download()).state, 'ready');
  assert.deepEqual(fs.readFileSync(file), payload); assert.deepEqual(fs.readFileSync(controller.stateStore.file), highWater);
});
test('cache recovery rejects links and non-files before fetching or replacing them', async t => {
  const { dir, controller, installer, network } = fixture(t); await controller.check(); await controller.download();
  const file = installer.receipt.file; const protectedFile = path.join(dir, 'unrelated-sentinel'); fs.writeFileSync(protectedFile, 'unrelated user data');
  fs.unlinkSync(file); fs.linkSync(protectedFile, file);
  let downloads = 0; const originalDownload = network.downloadFile; network.downloadFile = async (...args) => { downloads++; return originalDownload(...args); };
  await controller.check(); await assert.rejects(controller.download(), /链接/); assert.equal(downloads, 0); assert.equal(fs.readFileSync(protectedFile, 'utf8'), 'unrelated user data');
  fs.unlinkSync(file); fs.mkdirSync(file); await controller.check(); await assert.rejects(controller.download(), /普通文件/); assert.equal(downloads, 0); fs.rmdirSync(file);
  fs.writeFileSync(file, 'damaged');
  network.downloadFile = async (...args) => { await originalDownload(...args); fs.unlinkSync(file); fs.linkSync(protectedFile, file); };
  await controller.check(); await assert.rejects(controller.download(), /链接/); assert.equal(fs.lstatSync(file).nlink, 2);
  assert.equal(fs.readFileSync(protectedFile, 'utf8'), 'unrelated user data'); assert.equal(installer.invoked, undefined);
});
test('real locked NsisUpdater preparation and installation state bind verified local payload, never unsigned latest.yml', async t => {
  const dir = directory(t); const value = signed(); const release = verifyManifest(value.bytes, value.signature, policy); const stateStore = new ReleaseState(dir); stateStore.accept(release, policy, '1.0.0');
  const cache = path.join(dir, 'ota-pinned'); fs.mkdirSync(cache); const file = path.join(cache, '1-' + release.manifestSha256 + '-' + release.manifest.file); fs.writeFileSync(file, payload);
  const receipt = { ...value, release, file }; const config = path.join(dir, 'app-update.yml'); fs.writeFileSync(config, JSON.stringify(buildUpdateConfig(rawPolicy)));
  const adapter = { version: '1.0.0', name: 'test', isPackaged: true, baseCachePath: dir, userDataPath: dir, appUpdateConfigPath: config };
  const installer = createPinnedInstaller(policy, { dataDirectory: dir, currentVersion: '1.0.0', stateStore, appAdapter: adapter }); installer.on('error', () => {});
  await assert.rejects(installer.verifySignature(file), /没有/);
  await installer.prepareVerified(receipt); assert.equal(installer.installerPath, file); assert.equal(await installer.verifySignature(file), null);
  await assert.rejects(installer.verifyUpdateCodeSignature([], file), /禁止/);
  let spawned; installer.spawnLog = async (command, args) => { spawned = { command, args }; };
  assert.equal(installer.install(false, false), true); assert.equal(spawned.command, file); assert.deepEqual(spawned.args, ['--updated']);
  const second = createPinnedInstaller(policy, { dataDirectory: dir, currentVersion: '1.0.0', stateStore, appAdapter: adapter }); second.on('error', () => {}); await second.prepareVerified(receipt);
  let badSpawn = false; second.spawnLog = async () => { badSpawn = true; }; fs.writeFileSync(file, Buffer.alloc(payload.length)); assert.equal(second.install(false, false), false); assert.equal(badSpawn, false);
  assert.throws(() => verifyBoundInstallerSync(receipt, policy, '1.0.0', stateStore.load(), cache), /SHA256/);
});
test('pinned-key is an explicit separate strategy and unconfigured OTA stays disabled', t => {
  const dir = directory(t); const installer = new EventEmitter(); installer.prepareVerified = async () => {};
  assert.ok(createUpdateController(rawPolicy, { dataDirectory: dir, currentVersion: '1.0.0', confirm: async () => false, flush: async () => {}, installerFactory: () => installer }) instanceof PinnedUpdateController);
  assert.equal(createUpdateController({ enabled: false }).status().state, 'disabled');
});
test('transport rejects other origins/protocols/redirects/encoding and preserves TLS verification', async () => {
  for (const url of ['http://updates.example.invalid/crm/x', 'https://evil.invalid/crm/x', 'file:///C:/x', 'https://user:pass@updates.example.invalid/crm/x', 'https://updates.example.invalid/other/x', policy.feedUrl + '%2fescape', policy.feedUrl + 'x?token=1']) assert.equal(trustedUrl(url, policy), false);
  for (const responsePatch of [{ statusCode: 302, headers: { location: policy.feedUrl + 'other' } }, { statusCode: 200, headers: { 'content-encoding': 'gzip' } }, { statusCode: 200, headers: { 'content-length': '999' } }]) {
    await assert.rejects(responseFor(policy.feedUrl + 'manifest.json', policy, 64, (_url, options, callback) => {
      assert.equal(options.rejectUnauthorized, true); const request = new EventEmitter(); request.destroy = error => request.emit('error', error);
      queueMicrotask(() => { const response = new EventEmitter(); Object.assign(response, responsePatch); response.destroy = () => response.emit('close'); callback(response); }); return request;
    }));
  }
  const stream = limiter(1); stream.on('error', () => {}); await new Promise(resolve => stream.write(Buffer.from('too big'), error => { assert.ok(error); resolve(); }));
});
test('offline signer produces exact-byte Ed25519 manifest accepted by pinned client', t => {
  const dir = directory(t); const file = path.join(dir, 'PhilosopherStoneCRM-Setup-1.0.1-x64.exe'); fs.writeFileSync(file, payload);
  const release = signRelease(file, '1.0.1', 2, pair.privateKey); const verified = verifyManifest(release.bytes, release.signature, policy); assert.equal(verified.manifest.sha256, sha256(payload)); assert.equal(verified.manifest.sequence, 2);
});
test('test-only key generator protects new directory, emits no private data, refuses overwrite; real signing CLI works', { skip: process.platform !== 'win32' }, t => {
  fs.mkdirSync(path.join(root, '.validation'), { recursive: true }); const dir = path.join(root, '.validation', 'key-test-' + randomUUID()); t.after(() => { if (fs.existsSync(dir)) fs.rmSync(dir, { recursive: true, force: true }); });
  const ps = path.join(process.env.SystemRoot, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  const args = ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', path.join(root, 'scripts/generate-release-key.ps1'), '-Directory', dir, '-TestOnly'];
  const generated = spawnSync(ps, args, { encoding: 'utf8', shell: false }); assert.equal(generated.status, 0, generated.stderr); assert.equal(generated.stdout, '');
  const publicKey = fs.readFileSync(path.join(dir, 'public-key.pem'), 'utf8'); const id = fs.readFileSync(path.join(dir, 'key-id.txt'), 'utf8').trim();
  const fixtureDir = directory(t); const installer = path.join(fixtureDir, 'PhilosopherStoneCRM-Setup-1.0.1-x64.exe'); fs.writeFileSync(installer, payload); const out = path.join(fixtureDir, 'release');
  const result = spawnSync(process.execPath, [path.join(root, 'scripts/release-tools.cjs'), 'sign', dir, installer, '1.0.1', '1', out], { encoding: 'utf8', shell: false }); assert.equal(result.status, 0, result.stderr); assert.equal(result.stdout, '');
  assert.equal(verifyManifest(fs.readFileSync(path.join(out, 'manifest.json')), fs.readFileSync(path.join(out, 'manifest.sig')), validatePolicy({ ...rawPolicy, publicKey, keyId: id })).manifest.version, '1.0.1');
  assert.notEqual(spawnSync(ps, args, { encoding: 'utf8', shell: false }).status, 0);
});
