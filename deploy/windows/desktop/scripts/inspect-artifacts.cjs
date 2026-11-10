'use strict';
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const asar = require('@electron/asar');
const { getCurrentFuseWire, FuseV1Options } = require('@electron/fuses');
const root = path.resolve(__dirname, '..');
const hash = file => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
async function inspect(directory, version, acceptance, currentRelease = false) {
  const prefix = acceptance ? 'PhilosopherStoneCRM-Acceptance' : 'PhilosopherStoneCRM';
  const installer = path.join(directory, `${prefix}-Setup-${version}-x64.exe`);
  const executable = path.join(directory, 'win-unpacked', prefix + '.exe');
  const archive = path.join(directory, 'win-unpacked', 'resources', 'app.asar');
  const packaged = JSON.parse(asar.extractFile(archive, 'package.json').toString());
  assert.equal(packaged.version, version);
  assert.equal(packaged.name, acceptance ? 'philosopher-stone-crm-acceptance' : 'philosopher-stone-crm');
  assert.equal(packaged.main, acceptance ? 'src/acceptance-main.cjs' : 'src/main.cjs');
  const files = asar.listPackage(archive);
  if (!acceptance) assert.ok(!files.some(file => /acceptance|fixture|\.env|id_ed25519|\.pfx$/i.test(file)));
  const compared = [];
  for (const name of fs.readdirSync(path.join(root, 'src'))) {
    if (name === 'settings.cjs' && acceptance) continue;
    assert.deepEqual(asar.extractFile(archive, 'src/' + name), fs.readFileSync(path.join(root, 'src', name)), name + ' differs');
    compared.push(name);
  }
  const policy = JSON.parse(fs.readFileSync(path.join(directory, 'win-unpacked', 'resources', 'ota-policy.json'), 'utf8'));
  if (currentRelease) {
    assert.deepEqual(policy, JSON.parse(fs.readFileSync(path.join(root, 'release', 'ota-policy.json'), 'utf8')));
    const connection = JSON.parse(fs.readFileSync(path.join(directory, 'win-unpacked', 'resources', 'connection-policy.json'), 'utf8'));
    assert.deepEqual(connection, JSON.parse(fs.readFileSync(path.join(root, 'release', 'connection-policy.json'), 'utf8')));
    assert.equal(connection.httpsOrigin, 'https://8.133.190.46');
    assert.equal(connection.enabled, true);
    assert.equal(policy.trust, 'pinned-key-ed25519');
    assert.equal(policy.feedUrl, 'https://8.133.190.46/updates/windows/');
    assert.equal(policy.enabled, true);
    require('../src/signature.cjs').validatePolicy(policy);
  } else assert.equal(policy.enabled, false);
  const updateConfig = JSON.parse(fs.readFileSync(path.join(directory, 'win-unpacked', 'resources', 'app-update.yml'), 'utf8'));
  assert.equal(updateConfig.updaterCacheDirName, 'philosopher-stone-crm-updater');
  for (const license of ['LICENSE.electron.txt', 'LICENSES.chromium.html']) assert.ok(fs.statSync(path.join(directory, 'win-unpacked', license)).size > 0);
  const fuses = await getCurrentFuseWire(executable);
  for (const key of ['RunAsNode', 'EnableNodeOptionsEnvironmentVariable', 'EnableNodeCliInspectArguments']) assert.equal(fuses[FuseV1Options[key]], 48, key);
  for (const key of ['EnableEmbeddedAsarIntegrityValidation', 'OnlyLoadAppFromAsar']) assert.equal(fuses[FuseV1Options[key]], 49, key);
  return { version, acceptance, installer, bytes: fs.statSync(installer).size, sha256: hash(installer), executableSha256: hash(executable), archiveSha256: hash(archive), productionSourcesCompared: compared, fuses, ota: policy.enabled ? policy.trust : 'disabled' };
}
(async () => {
  const results = [];
  if (process.argv[2] === '--release') {
    const version = require('../package.json').version;
    results.push(await inspect(path.join(root, 'dist-' + version), version, false, true));
  } else {
    for (const [directory, version, acceptance] of [['dist', '1.0.0', false], ['dist-next', '1.0.1', false], ['.validation/acceptance-1.0.0', '1.0.0', true], ['.validation/acceptance-1.0.1', '1.0.1', true]]) results.push(await inspect(path.join(root, directory), version, acceptance));
  }
  console.log(JSON.stringify({ node: process.version, platform: process.platform, arch: process.arch, results }, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
