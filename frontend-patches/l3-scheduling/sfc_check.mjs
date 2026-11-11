import crypto from 'node:crypto'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const manifest = JSON.parse(fs.readFileSync(path.join(here, 'manifest.json'), 'utf8'))
const target = manifest.targets[0]
const frontendRoot = process.argv[2]

if (!frontendRoot) {
  console.error('usage: node sfc_check.mjs <crm-frontend-root-with-node_modules>')
  process.exit(2)
}
if (manifest.targets.length !== 1) {
  throw new Error('This check covers the single navigation target only')
}

const require = createRequire(path.join(frontendRoot, 'index.js'))
let compiler
try {
  compiler = require('vue/compiler-sfc')
} catch (error) {
  console.error(
    'SKIP: vue/compiler-sfc is not resolvable from ' +
      frontendRoot +
      ' (' +
      error.message +
      '). Point the argument at the fixed CRM frontend tree; no install is attempted.',
  )
  process.exit(3)
}

const sha = (data) => crypto.createHash('sha256').update(data).digest('hex')

function applyEdits(text) {
  for (const edit of target.edits) {
    const count = text.split(edit.anchor).length - 1
    if (count !== 1) {
      throw new Error('anchor count ' + count + ' for ' + edit.anchor.slice(0, 60))
    }
    text = text.replace(edit.anchor, () => edit.replacement)
  }
  return text
}

function compile(name, source) {
  const { descriptor, errors } = compiler.parse(source, { filename: name })
  if (errors.length) {
    throw new Error(name + ' parse errors: ' + errors.map(String).join('; '))
  }
  if (!descriptor.scriptSetup || !descriptor.template) {
    throw new Error(name + ' is missing <script setup> or <template>')
  }
  const script = compiler.compileScript(descriptor, { id: name })
  const template = compiler.compileTemplate({
    source: descriptor.template.content,
    filename: name,
    id: name,
    compilerOptions: { bindingMetadata: script.bindings },
  })
  if (template.errors.length) {
    throw new Error(name + ' template errors: ' + template.errors.map(String).join('; '))
  }
  return { script, template }
}

for (const baseline of target.baselines) {
  const fixture = fs.readFileSync(path.join(here, baseline.fixture), 'utf8')
  if (sha(fixture) !== baseline.before) {
    throw new Error('fixture hash differs from declared baseline: ' + baseline.fixture)
  }
  compile('baseline-' + baseline.name + '.vue', fixture)

  const patched = applyEdits(fixture)
  if (sha(patched) !== baseline.after) {
    throw new Error('patched hash differs from declared after: ' + baseline.name)
  }
  const { script, template } = compile('patched-' + baseline.name + '.vue', patched)

  for (const binding of ['isCrmUser', 'LucideCalendarClock', 'selectItem']) {
    if (!(binding in script.bindings)) {
      throw new Error('missing setup binding ' + binding + ' for ' + baseline.name)
    }
  }
  if (!template.code.includes('/team-schedule')) {
    throw new Error('compiled template lost the /team-schedule href for ' + baseline.name)
  }
  console.log('PASS SFC compile: ' + baseline.name + ' -> ' + sha(patched))
}

console.log('PASS: both baselines and both patched variants compile with vue/compiler-sfc')
