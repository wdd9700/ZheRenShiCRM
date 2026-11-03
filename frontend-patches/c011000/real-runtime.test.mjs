import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { createRequire } from 'node:module'
import { execFileSync } from 'node:child_process'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import { webcrypto } from 'node:crypto'
import { fileURLToPath } from 'node:url'

const root = process.env.C011100_FRONTEND_ROOT
if (!root) throw Error('C011100_FRONTEND_ROOT must point to the fixed exported frontend with existing node_modules')
const require = createRequire(resolve(root, 'package.json'))
assert.equal(require('vue/package.json').version, '3.5.32')
assert.equal(require('pinia/package.json').version, '2.3.1')
const vue = require('vue'), pinia = require('pinia')
const tick = () => new Promise(resolve => setImmediate(resolve))
const here = fileURLToPath(new URL('.', import.meta.url))
const sources = JSON.parse(execFileSync('python', ['-c',
  "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from source_edits import SOURCE_EDITS,transform;p=Path(sys.argv[2]).parent;print(json.dumps({t:transform(t,(p/t).read_bytes()).decode('utf-8') for t in SOURCE_EDITS}))",
  here, root], { encoding: 'utf8' }))
const documentCode = sources['frontend/src/data/document.js']

test('all strict transformed JS/TS/JSX and Vue script blocks parse using the fixed Babel parser', () => {
  const { parse } = require('@babel/parser')
  for (const [path, source] of Object.entries(sources)) {
    const script = path.endsWith('.vue') ? source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1] : source
    assert.doesNotThrow(() => parse(script, { sourceType: 'module', plugins: ['typescript', 'jsx'] }), path)
  }
})

async function fixture({ routeName = 'Lead', create = false } = {}) {
  let hidden = false, identity = 'Synthetic Sales', covered = true, fail = false
  let readable = true, writable = true, creatable = true, current, session
  const events = {}, requests = [], runtimes = [], config = {}
  const fields = [{ fieldname: 'title', fieldtype: 'Data' }]
  const route = { name: routeName, fullPath: routeName.endsWith('s') ? '/leads?status=New' : '/leads/SYNTHETIC-1#activity',
    hash: '#activity', params: routeName.endsWith('s') ? {} : { leadId: 'SYNTHETIC-1' } }
  const elements = []
  const dom = { querySelector: () => null, body: { append: x => elements.push(x) }, createElement() {
    return { style: {}, children: [], setAttribute() {}, append(...children) { this.children.push(...children) }, remove() {} }
  } }
  const env = { crypto: webcrypto, cookie: () => 'synthetic-stable', hidden: () => hidden,
    on: (type, fn) => { events[type] = fn }, cover: () => { covered = true }, uncover: () => { covered = false },
    identify: async () => identity, broadcast() {} }
  const context = createContext({ __env: env, Uint32Array, AbortController, Event, console,
    setTimeout, clearTimeout, document: dom, window: { location: {} } })
  const modules = new Map()
  function synthetic(id, values) {
    if (!modules.has(id)) modules.set(id, new SyntheticModule(Object.keys(values), function () {
      for (const [key, value] of Object.entries(values)) this.setExport(key, value)
    }, { context, identifier: id }))
    return modules.get(id)
  }
  let boundary
  async function request({ url, params }) {
    boundary.assertRequest(boundary.epoch, url)
    requests.push({ url, params })
    if (fail) throw Error('Synthetic offline')
    if (url === 'frappe.client.get_doc_permissions') return { permissions: { read: readable, write: writable } }
    if (url === 'frappe.client.has_permission') return { has_permission: params.perm_type === 'create' ? creatable : readable }
    if (url === 'frappe.client.get') return { name: 'SYNTHETIC-1', doctype: 'CRM Lead', title: 'server' }
    if (url === 'frappe.desk.form.load.getdoctype') return { docs: [{ name: params.doctype, fields }], user_settings: '{}' }
    if (url === 'crm.api.doc.get_assigned_users') return []
    if (url === 'crm.api.activities.get_activities') return [[], [], [], [], []]
    if (url === 'crm.api.doc.get_data') return { data: [{ name: 'SYNTHETIC-1' }] }
    throw Error('Unexpected endpoint: ' + url)
  }
  config.resourceFetcher = request
  const host = () => ({ children: [], parent: null, text: '' })
  const container = host()
  const renderer = vue.createRenderer({ createElement: host, createText: text => ({ ...host(), text }), createComment: host,
    setText(node, text) { node.text = text }, setElementText(node, text) { node.text = text },
    insert(node, parent) { node.parent = parent; parent.children.push(node) },
    remove(node) { if (node.parent) node.parent.children = node.parent.children.filter(child => child !== node) },
    parentNode: node => node.parent, nextSibling: () => null, patchProp() {} })
  const router = { currentRoute: vue.ref(route), resolve: () => route, isReady: async () => {}, install() {} }
  const plugin = { install() {} }
  const resources = new Set(['resources', 'documentResource', 'listResource', 'local', 'accountBoundary'])
  const business = {
    '@/data/script': { getScript: () => ({ setupScript: async () => [], scripts: vue.ref([]) }) },
    '@/stores/global': { globalStore: () => ({}) },
    '@/utils/model.js': { noValueFieldTypes: [], standardFieldsMeta: [] },
    '@/utils/numberFormat.js': { formatCurrency: value => value, formatNumber: value => value },
    '@/composables/useAttachments': { useAttachments: () => ({ trackOldFile() {}, processPendingDeletions() {} }) },
    '@/composables/settings': { showSettings: vue.ref(false), activeSettingsPage: vue.ref('') },
    '@/utils': { runSequentially: async tasks => { for (const task of tasks) await task() }, parseAssignees: x => x, sanitizeText: x => x },
    '@/utils/fieldTransforms': { findMissingMandatory: () => [] },
    '@/utils/fetchFrom': { getFetchSource: () => ({}), getFieldsToFetch: () => [], getPendingFetchFields: () => [], getSourceFieldnames: () => [] },
  }
  const App = vue.defineComponent({ setup() {
    session = modules.get('session').namespace.sessionStore()
    current = modules.get('document').namespace.useDocument('CRM Lead', create ? '' : 'SYNTHETIC-1')
    const safe = modules.get('safeResume').namespace
    let cleanup
    vue.onMounted(() => {
      cleanup = safe.registerResumePage(routeName, () => ({ doctype: 'CRM Lead', filters: { status: 'New' }, page_length: 20 }))
      if (!routeName.endsWith('s')) safe.registerResumeSection('activity:SYNTHETIC-1')
    })
    vue.onUnmounted(() => cleanup?.())
    return () => vue.h('p', current.document.doc?.title || '')
  } })
  async function load(id) {
    if (modules.has(id)) return modules.get(id)
    if (id === 'vue') return synthetic(id, { ...vue, createApp(component) {
      const app = renderer.createApp(component), mount = app.mount
      app.mount = () => mount(container)
      runtimes.push({ app })
      return app
    } })
    if (id === 'pinia') return synthetic(id, { ...pinia, createPinia() {
      const instance = pinia.createPinia(); runtimes.push({ pinia: instance }); return instance
    } })
    if (id === 'config') return synthetic(id, { getConfig: key => config[key] })
    if (id === 'debounce') return synthetic(id, { default: fn => fn })
    if (id === 'request') return synthetic(id, { request })
    if (id === 'realtime') return synthetic(id, { onDocUpdate() {} })
    if (id === 'socketAccess') return synthetic(id, { readSocket() {} })
    if (id === 'frappe-ui') {
      const generic = await load('resources'), doc = await load('documentResource')
      if (generic.status === 'unlinked') await generic.link(link)
      if (doc.status === 'unlinked') await doc.link(link)
      await generic.evaluate(); await doc.evaluate()
      return synthetic(id, { ...generic.namespace, ...doc.namespace, FrappeUI: plugin, Button: {}, TextInput: {}, FormControl: {},
        ErrorMessage: {}, Dialog: {}, Alert: {}, Badge: {}, setConfig(key, value) { config[key] = value },
        frappeRequest: request, call: (url, params) => request({ url, params }), toast: { error() {}, success() {} } })
    }
    if (business[id]) return synthetic(id, business[id])
    let code
    if (id === 'document') code = documentCode
    else if (id === 'meta') code = sources['frontend/src/stores/meta.js']
    else {
      const path = resources.has(id) ? `./payload/resources/${id}.${id === 'local' ? 'ts' : 'js'}` : `./payload/${id}.js`
      code = await readFile(new URL(path, import.meta.url), 'utf8')
    }
    if (id === 'accountBoundary') code = code.replace('createAccountBoundary(browserEnvironment())', 'createAccountBoundary(globalThis.__env)')
    if (id === 'local') code = code.replace(/<T = any>/g, '').replace(/: Promise<(?:T \| null|null)>/g, '').replace(/: string/g, '').replace(/: T/g, '')
    if (id === 'main') code = code.replaceAll('import.meta.env.DEV', 'false')
    const mod = new SourceTextModule(code, { context, identifier: id }); modules.set(id, mod); return mod
  }
  function link(specifier) {
    if (specifier === './index.css') return synthetic(specifier, {})
    if (specifier === './App.vue') return synthetic(specifier, { default: App })
    if (specifier === './router') return synthetic(specifier, { default: router })
    if (specifier === './translation') return synthetic(specifier, { default: plugin })
    if (specifier === './utils/dialogs') return synthetic(specifier, { createDialog() {} })
    if (specifier === './socket') return synthetic(specifier, { initSocket() {
      const socket = { disconnected: false, removeAllListeners() {}, disconnect() { this.disconnected = true } }
      runtimes.push({ socket }); return socket
    } })
    if (specifier === '@framework/ui/telemetry') return synthetic(specifier, { telemetryPlugin: plugin })
    if (specifier === 'frappe-ui/experimental') return synthetic(specifier, { spritePlugin: plugin })
    if (business[specifier] || ['vue', 'pinia', 'frappe-ui'].includes(specifier)) return load(specifier)
    return load(specifier.split('/').at(-1))
  }
  async function namespace(id) {
    const mod = await load(id)
    if (mod.status === 'unlinked') await mod.link(link)
    if (mod.status !== 'evaluated') await mod.evaluate()
    return mod.namespace
  }
  boundary = (await namespace('accountBoundary')).accountBoundary
  await boundary.resume()
  await namespace('session'); await namespace('safeResume'); await namespace('document')
  await namespace('main'); await tick(); await vue.nextTick()
  assert.equal(boundary.state, 'ACTIVE'); assert.equal(session.user, 'Synthetic Sales')
  return { boundary, requests, fields, runtimes, namespace, route,
    get current() { return current }, get session() { return session }, get covered() { return covered },
    identity(value) { identity = value }, permission(read, write = true, create = true) { readable = read; writable = write; creatable = create },
    offline(value) { fail = value },
    hide(value) { hidden = value; events.visibilitychange() },
    async resume() { hidden = false; events.visibilitychange(); await boundary.resume(); await tick(); await vue.nextTick() },
    close() { boundary.lock() },
  }
}

test('real Vue/Pinia, actual main/session/useDocument rebuild default activity and restore scalar draft only explicitly', async () => {
  const f = await fixture(), old = f.current, safe = await f.namespace('safeResume')
  old.document.doc.title = 'unsubmitted'
  const initialPinia = f.runtimes.find(item => item.pinia).pinia
  f.hide(true)
  assert.equal(f.covered, true); assert.equal(initialPinia._s.size, 0)
  assert.deepEqual(Object.keys(initialPinia.state.value), [])
  assert.ok(f.runtimes.find(item => item.socket).socket.disconnected)
  await f.resume()
  assert.equal(f.boundary.state, 'ACTIVE'); assert.equal(f.covered, false)
  assert.notEqual(f.current.document, old.document); assert.equal(old.document.doc, null)
  assert.equal(f.current.document.doc.title, 'server')
  const [plan] = safe.planDrafts(f.boundary.user)
  assert.equal(plan.values.title, 'unsubmitted'); assert.equal(safe.restoreDraft(plan), true)
  assert.equal(f.current.document.doc.title, 'unsubmitted')
  await assert.rejects(old.triggerOnChange('title', 'stale'), /locked/)
  assert.ok(f.requests.some(item => item.url === 'crm.api.activities.get_activities'))
  assert.ok(f.requests.every(item => !/set_value|insert|delete|run_doc_method/.test(item.url)))
  f.hide(true); await f.resume(); assert.equal(f.boundary.state, 'ACTIVE')
  assert.equal(f.session.user, 'Synthetic Sales'); f.close()
})

test('real runtime retry retains separate drafts; read revocation and changed identity destroy old domain', async () => {
  for (const mode of ['offline', 'permission', 'Guest', 'Other Account']) {
    const f = await fixture(), old = f.current.document
    old.doc.title = 'private draft'; f.hide(true)
    if (mode === 'offline') f.offline(true)
    else if (mode === 'permission') f.permission(false)
    else f.identity(mode)
    await f.resume()
    assert.equal(f.covered, true)
    if (mode === 'offline') {
      assert.equal(f.boundary.state, 'RETRY_COVERED')
      f.offline(false); await f.boundary.resume(); await tick()
      assert.equal(f.boundary.state, 'ACTIVE')
      assert.equal((await f.namespace('safeResume')).planDrafts(f.boundary.user).length, 1)
    } else {
      assert.equal(f.boundary.state, 'IDENTITY_REQUIRED'); assert.equal(old.doc, null)
      assert.equal((await f.namespace('safeResume')).planDrafts('Synthetic Sales').length, 0)
    }
    f.close()
  }
})

test('real runtime list keeps current params and creation draft uses fresh create permission', async () => {
  for (const allowed of [true, false]) {
    const f = await fixture({ routeName: 'Leads', create: true })
    f.current.document.doc.title = 'new draft'; f.hide(true)
    f.permission(true, false, allowed); await f.resume()
    const safe = await f.namespace('safeResume')
    if (allowed) {
      assert.equal(f.boundary.state, 'ACTIVE')
      const listRead = f.requests.find(item => item.url === 'crm.api.doc.get_data')
      assert.equal(listRead.params.filters.status, 'New')
      assert.equal(listRead.params.page_length, 20)
      assert.equal(f.current.document.doc.title, undefined)
      assert.equal(safe.planDrafts(f.boundary.user).length, 1)
    } else assert.equal(f.covered, true)
    f.close()
  }
})
