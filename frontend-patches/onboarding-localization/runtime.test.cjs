const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const [root, modules, catalogPath, translationPath] = process.argv.slice(2);
const compiler = require(path.join(modules, 'vue/node_modules/@vue/compiler-sfc'));
const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
const dir = path.join(root, 'ui/src/components/Onboarding');
const sources = {};
for (const name of ['GettingStartedBanner.vue', 'HelpModal.vue', 'OnboardingSteps.vue']) {
  const source = sources[name] = fs.readFileSync(path.join(dir, name), 'utf8');
  const parsed = compiler.parse(source, { filename: path.join(dir, name) });
  assert.deepEqual(parsed.errors, [], name);
  const script = compiler.compileScript(parsed.descriptor, { id: name, fs: {
    fileExists: fs.existsSync, readFile: filename => fs.readFileSync(filename, 'utf8'),
  } });
  const template = compiler.compileTemplate({
    source: parsed.descriptor.template.content, filename: name, id: name,
    compilerOptions: { bindingMetadata: script.bindings },
  });
  assert.deepEqual(template.errors, [], name);
  assert(source.includes('getCurrentInstance()?.appContext.config.globalProperties.__'));
  assert(source.includes('appName: "frappecrm"'));
  assert(source.includes('useOnboarding(props.appName)!'));
}
const banner = sources['GettingStartedBanner.vue'];
assert(banner.includes('theme="gray"\n\t\t\tvariant="subtle"'));
for (const expected of ['@click="openOnboarding"', 'showHelpCenter = true;', 'isOnboardingStepsCompleted = true;', 'showHelpModal.value = true;']) assert(banner.includes(expected));
const modal = sources['HelpModal.vue'];
for (const expected of [':appName="appName"', ':afterSkip="afterSkip"', ':afterSkipAll="afterSkipAll"', ':afterReset="afterReset"', ':afterResetAll="afterResetAll"', 'syncStatus();', 'resetAll();']) assert(modal.includes(expected));
const steps = sources['OnboardingSteps.vue'];
for (const expected of ['resetAll(afterResetAll)', 'skipAll(afterSkipAll)', 'skip(step.name, afterSkip)', 'reset(step.name, afterReset)', 'step.onClick?.()']) assert(steps.includes(expected));

const code = fs.readFileSync(translationPath, 'utf8')
  .replace("import { getConfig } from 'frappe-ui'", '')
  .replace("import chineseMessages from './philosopher-zh-cn.json'", '')
  .replace('export default function translationPlugin', 'function translationPlugin');
function translateFor(language, server = {}) {
  const window = {philosopher_language: language};
  const app = {config: {globalProperties: {}}};
  vm.runInNewContext(code + '\ntranslationPlugin(app)', {
    app, window, chineseMessages: catalog, getConfig: () => server,
  });
  return app.config.globalProperties.__;
}
const welcome = steps.match(/\{\{ (translate\("Welcome to \{0\}"[^\n]+) \}\}/)[1];
const count = steps.match(/\{\{ (translate\("\{0\}\/\{1\} steps completed"[^\n]+) \}\}/)[1];
function evaluate(expression, translate) {
  return vm.runInNewContext(expression, {translate, title: 'Frappe CRM', stepsCompleted: 2, totalSteps: 5});
}
assert.equal(evaluate(welcome, translateFor('zh-CN')), '欢迎使用哲人石CRM');
assert.equal(evaluate(count, translateFor('zh-CN')), '已完成 2/5 步');
assert.equal(evaluate(welcome, translateFor('en')), 'Welcome to Frappe CRM');
assert.equal(evaluate(count, translateFor('fr', {'{0}/{1} steps completed': '{0}/{1} étapes terminées'})), '2/5 étapes terminées');
console.log('PASS: fixed Vue SFC compilation, scoped translator wiring, display expressions, controls and callback arguments');
