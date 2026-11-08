const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const [translationPath, catalogPath, schedulePath] = process.argv.slice(2);
const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
const placeholders = value => [...value.matchAll(/\{\d+\}/g)].map(match => match[0]).sort();
for (const [key, value] of Object.entries(catalog)) {
  assert.deepEqual(placeholders(value), placeholders(key), key);
}
assert.equal(catalog.Lead, '线索');
assert.equal(catalog.Deal, '商机');
assert.equal(catalog.Organization, '企业');
assert.equal(catalog.Contact, '联系人');
assert.equal(catalog.Note, '备注');
assert.equal(catalog.Task, '任务');

const code = fs.readFileSync(translationPath, 'utf8')
  .replace("import { getConfig } from 'frappe-ui'", '')
  .replace("import chineseMessages from './philosopher-zh-cn.json'", '')
  .replace('export default function translationPlugin', 'function translationPlugin');
let server = {};
const window = {philosopher_language: 'zh-CN'};
const app = {config: {globalProperties: {}}};
const sandbox = {window, chineseMessages: {...catalog, 'Context:field': '词典上下文'}, getConfig: () => server};
vm.runInNewContext(code + '\ntranslationPlugin(app)', {...sandbox, app});
const translate = app.config.globalProperties.__;
assert.equal(translate, window.__);
assert.equal(translate('Lead'), '线索');
assert.equal(translate('Mandatory field error: {0}', ['姓名']), '必填字段错误：姓名');
assert.equal(translate('Untranslated {0} {1}', ['X']), 'Untranslated X {1}');
assert.equal(translate('Context', [], 'field'), '词典上下文');
server = {'Lead': '服务端线索', 'Context:field': '服务端上下文', 'Only server': '服务端消息'};
assert.equal(translate('Lead'), '服务端线索');
assert.equal(translate('Context', [], 'field'), '服务端上下文');
assert.equal(translate('Only server'), '服务端消息');
for (const language of ['zh', 'zh_CN', 'zh-Hans', 'zh-Hans-CN']) {
  window.philosopher_language = language;
  assert.equal(translate('Deal'), '商机', language);
}
for (const language of ['en', 'fr', 'zh-TW', 'zh-Hant', '', null]) {
  window.philosopher_language = language;
  assert.equal(translate('Deal'), 'Deal', String(language));
  assert.equal(translate('Only server'), '服务端消息');
}
const scope = {window: {}};
vm.runInNewContext(fs.readFileSync(schedulePath, 'utf8'), scope);
const text = scope.window.PhilosopherCRMText;
for (const part of [text, text.enums, text.timeline, text.icsActions, text.errors, text.dates]) {
  assert(Object.isFrozen(part));
}
assert.equal(text.enums.Busy, '占用');
assert.equal(text.enums.Active, '进行中');
assert.equal(text.timeline.empty, '所选日期没有日程');
assert.equal(text.icsActions.local_conflict, '本地修改冲突');
assert(text.errors.DUPLICATE_UID);
console.log('PASS: catalog placeholders, native translation, locales, server precedence, schedule contract');
