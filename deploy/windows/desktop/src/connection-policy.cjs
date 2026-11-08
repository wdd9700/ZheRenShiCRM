'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { defaults, validateConnection } = require('./settings.cjs');
function readConnectionPolicy(resources) {
  const file = path.join(resources, 'connection-policy.json');
  if (!fs.existsSync(file)) return null;
  const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (raw.enabled !== true) return null;
  return validateConnection({ ...defaults().connection, mode: 'https', trustedHttps: true, httpsOrigin: raw.httpsOrigin });
}
function initializeConnection(store, connection) {
  if (!connection || fs.existsSync(store.file)) return false;
  store.save(connection); return true;
}
module.exports = { readConnectionPolicy, initializeConnection };
