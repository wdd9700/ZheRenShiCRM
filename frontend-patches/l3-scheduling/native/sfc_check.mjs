import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'

const [root, compilerRoot] = process.argv.slice(2)
if (!root || !compilerRoot) throw new Error('usage: node sfc_check.mjs <applied CRM root> <fixed CRM frontend with node_modules>')
const require = createRequire(path.resolve(compilerRoot, 'index.js'))
const compiler = require('vue/compiler-sfc')

function compile(filename) {
  const source = fs.readFileSync(path.join(root, filename), 'utf8')
  const { descriptor, errors } = compiler.parse(source, { filename })
  assert.deepEqual(errors, [])
  const script = compiler.compileScript(descriptor, { id: filename })
  const template = compiler.compileTemplate({
    source: descriptor.template.content, filename, id: filename,
    compilerOptions: { bindingMetadata: script.bindings },
  })
  assert.deepEqual(template.errors, [])
  return [script.content, template.code]
}

const [sidebar, nav] = compile('frontend/src/components/Layouts/AppSidebar.vue')
assert.match(nav, /route:\s*\{ name: 'TeamSchedule' \}/)
assert.match(nav, /active:\s*[^\n]+route\.name === 'TeamSchedule'/)
assert.match(nav, /isCrmUser\(\)/)
assert.match(sidebar, /mobileSidebarOpened\.value = false/)
assert.doesNotMatch(nav, /href: [^\n]*team-schedule/)
const [page, work] = compile('frontend/src/pages/TeamSchedule.vue')
assert.match(work, /团队日程/)
assert.match(work, /\$setup\["LayoutHeader"\]/)
assert.match(work, /\$setup\["Button"\]/)
assert.match(work, /id:\s*"schedule-form"/)
assert.doesNotMatch(work, /iframe|schedule-return-bar|AppSidebar/)
assert.match(page, /accountBoundary\.onInvalidate\(stop\)/)
assert.match(page, /removeEventListener\('crm-team-schedule-active', start\)/)
console.log('PASS real Vue SFC compiler: native TeamSchedule page + branded CRM AppSidebar')
