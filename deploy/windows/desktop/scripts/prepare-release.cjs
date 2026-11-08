'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { buildUpdateConfig } = require('../src/updater.cjs');
function prepare() {
  const directory = path.join(__dirname, '..', 'release');
  const policy = JSON.parse(fs.readFileSync(path.join(directory, 'ota-policy.json'), 'utf8'));
  require('../src/connection-policy.cjs').readConnectionPolicy(directory);
  fs.writeFileSync(path.join(directory, 'app-update.yml'), JSON.stringify(buildUpdateConfig(policy), null, 2) + '\n');
}
module.exports = prepare;
if (require.main === module) prepare();
