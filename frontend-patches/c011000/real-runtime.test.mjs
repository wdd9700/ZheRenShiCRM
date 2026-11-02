import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createRequire } from 'node:module'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import { webcrypto } from 'node:crypto'

const root = process.env.C011100_FRONTEND_ROOT
if (!root) throw Error('C011100_FRONTEND_ROOT must point to the fixed exported frontend with existing node_modules')
const require = createRequire(resolve(root, 'package.json'))
assert.equal(require('vue/package.json').version, '3.5.32')
assert.equal(require('pinia/package.json').version, '2.3.1')
const vue = require('vue')
const pinia = require('pinia')
const tick = () => new Promise(resolve => setImmediate(resolve))

test('fixed real Vue renderer and Pinia execute actual main and session setup after identity only', async () => {
  for (const mode of ['normal', 'Guest', 'hidden', 'sprite']) {
    const events = {}
    const covers = []
    let hidden = false
    let resolveIdentity
    let setups = 0
    let session
    const env = { crypto: webcrypto, cookie: () => 'synthetic-stable', hidden: () => hidden,
      on: (type, fn) => { events[type] = fn }, cover: text => covers.push(text), uncover() {},
      identify: () => new Promise(resolve => { resolveIdentity = resolve }), broadcast() {} }
    const context = createContext({ __env: env, Uint32Array, window: { location: {} } })
    const modules = new Map()
    function synthetic(id, values) {
      if (!modules.has(id)) modules.set(id, new SyntheticModule(Object.keys(values), function () {
        for (const [key, value] of Object.entries(values)) this.setExport(key, value)
      }, { context }))
      return modules.get(id)
    }
    const boundaryCode = (await readFile(new URL('./payload/resources/accountBoundary.js', import.meta.url), 'utf8'))
      .replace('createAccountBoundary(browserEnvironment())', 'createAccountBoundary(globalThis.__env)')
    const boundaryModule = new SourceTextModule(boundaryCode, { context })
    await boundaryModule.link(() => { throw Error('Unexpected boundary import') })
    await boundaryModule.evaluate()
    const boundary = boundaryModule.namespace.accountBoundary
    const sessionModule = new SourceTextModule(await readFile(new URL('./payload/session.js', import.meta.url), 'utf8'), { context })
    await sessionModule.link(specifier => specifier.endsWith('/accountBoundary') ? boundaryModule
      : synthetic(specifier, specifier === 'vue' ? vue : specifier === 'pinia' ? pinia
        : { createResource: options => ({ options }) }))
    await sessionModule.evaluate()
    const host = () => ({ children: [], parent: null, text: '' })
    const container = host()
    const renderer = vue.createRenderer({
      createElement: host, createText: text => ({ ...host(), text }), createComment: host,
      setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.text = text },
      insert(node, parent) { node.parent = parent; parent.children.push(node) },
      remove(node) { node.parent.children = node.parent.children.filter(child => child !== node) },
      parentNode: node => node.parent, nextSibling: () => null, patchProp() {},
    })
    const App = vue.defineComponent({ setup() {
      setups++
      session = sessionModule.namespace.sessionStore()
      return () => vue.h('p', session.isLoggedIn ? 'Synthetic signed in' : 'Not signed in')
    } })
    let actualPinia
    let actualApp
    const plugin = () => ({ install() {} })
    const code = (await readFile(new URL('./payload/main.js', import.meta.url), 'utf8'))
      .replaceAll('import.meta.env.DEV', 'false')
    const main = new SourceTextModule(code, { context })
    await main.link(specifier => {
      if (specifier.endsWith('/accountBoundary')) return boundaryModule
      const values = specifier === './index.css' ? {}
        : specifier === 'vue' ? { createApp(component) {
          actualApp = renderer.createApp(component)
          const mount = actualApp.mount
          actualApp.mount = () => mount(container)
          return actualApp
        } }
        : specifier === 'pinia' ? { createPinia() { actualPinia = pinia.createPinia(); return actualPinia } }
        : specifier === './App.vue' ? { default: App }
        : specifier === './router' || specifier === './translation' ? { default: plugin() }
        : specifier === './socket' ? { initSocket: () => ({}) }
        : specifier === './utils/dialogs' ? { createDialog() {} }
        : specifier === '@framework/ui/telemetry' ? { telemetryPlugin: plugin() }
        : specifier === 'frappe-ui/experimental' ? { spritePlugin: { install() {
          if (mode === 'sprite') throw Error('Synthetic plugin error')
        } } }
        : { FrappeUI: plugin(), Button: {}, TextInput: {}, FormControl: {}, ErrorMessage: {},
          Dialog: {}, Alert: {}, Badge: {}, setConfig() {}, frappeRequest() {} }
      return synthetic('main:' + specifier, values)
    })
    await main.evaluate()
    await tick()
    assert.equal(setups, 0)
    assert.equal(actualApp, undefined)
    if (mode === 'hidden') {
      hidden = true; events.visibilitychange(); hidden = false; events.visibilitychange()
    }
    resolveIdentity(mode === 'Guest' ? 'Guest' : 'Synthetic Sales')
    await boundary.ready
    await tick()
    if (mode === 'normal') {
      assert.equal(boundary.diagnostic.stage, 'READY')
      assert.equal(boundary.diagnostic.failure, 'NONE')
      assert.equal(setups, 1)
      assert.equal(session.user, 'Synthetic Sales')
      assert.equal(session.isLoggedIn, true)
      assert.equal(actualPinia._s.get('crm-session'), session)
      assert.equal(container.children[0].text, 'Synthetic signed in')
      actualApp.unmount()
    } else {
      assert.equal(setups, 0)
      assert.equal(container.children.length, 0)
      assert.equal(boundary.diagnostic.failure, mode === 'Guest' ? 'IDENTITY_INVALID'
        : mode === 'hidden' ? 'PAGE_HIDDEN' : 'PLUGIN_EXCEPTION')
      assert.ok(covers.length >= 2)
    }
    if (actualPinia) pinia.disposePinia(actualPinia)
  }
})
