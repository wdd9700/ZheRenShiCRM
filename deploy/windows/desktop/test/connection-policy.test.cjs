'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { SettingsStore, defaults } = require('../src/settings.cjs');
const { readConnectionPolicy, initializeConnection } = require('../src/connection-policy.cjs');
function fixture(t) { const base = path.join(__dirname, '../.validation'); fs.mkdirSync(base, { recursive: true }); const dir = fs.mkdtempSync(path.join(base, 'connection-')); t.after(() => fs.rmSync(dir, { recursive: true, force: true })); return dir; }
test('unconfigured dedicated HTTPS endpoint makes no guesses or profile changes', t => {
  const dir = fixture(t); fs.writeFileSync(path.join(dir, 'connection-policy.json'), '{"enabled":false}'); const store = new SettingsStore(path.join(dir, 'profile'));
  assert.equal(readConnectionPolicy(dir), null); assert.equal(initializeConnection(store, null), false); assert.equal(fs.existsSync(store.file), false);
});
test('trusted build may initialize only a fresh profile to fixed HTTPS, never overwrite an old origin', t => {
  const dir = fixture(t); fs.writeFileSync(path.join(dir, 'connection-policy.json'), JSON.stringify({ enabled: true, httpsOrigin: 'https://crm.example.invalid' }));
  const connection = readConnectionPolicy(dir); const store = new SettingsStore(path.join(dir, 'new'));
  assert.equal(initializeConnection(store, connection), true); assert.equal(store.value.connection.mode, 'https'); assert.equal(store.value.connection.httpsOrigin, 'https://crm.example.invalid');
  const old = new SettingsStore(path.join(dir, 'old')); old.write(defaults()); const bytes = fs.readFileSync(old.file);
  assert.equal(initializeConnection(old, connection), false); assert.deepEqual(fs.readFileSync(old.file), bytes); assert.equal(old.value.connection.mode, 'external');
});
test('dedicated endpoint policy cannot lower TLS or inject credentials/path', t => {
  const dir = fixture(t); for (const httpsOrigin of ['http://8.133.190.46', 'https://user:pass@example.invalid', 'https://example.invalid/path']) {
    fs.writeFileSync(path.join(dir, 'connection-policy.json'), JSON.stringify({ enabled: true, httpsOrigin })); assert.throws(() => readConnectionPolicy(dir));
  }
});
