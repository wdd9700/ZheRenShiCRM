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
const python = process.env.C011100_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')
const sources = JSON.parse(execFileSync(python, [resolve(here, 'runtime_sources.py'),
  process.env.C011100_SOURCE_ROOT || root], { encoding: 'utf8' }))

test('runtime evidence accepts only the audited three navigation edits and preserves exact resume guards', () => {
  execFileSync(python, ['-c', `import sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from runtime_sources import SIDEBAR,NAV_AFTER,HERE,sha,navigation_contract,normalize_source
from source_edits import SOURCE_EDITS,transform
manifest={e['target']:e for e in json.loads((HERE/'manifest.json').read_text())}
entry=manifest[SIDEBAR]
edits=navigation_contract(entry)
actual=json.loads(sys.stdin.buffer.read().decode('utf-8'))
after=actual[SIDEBAR]
if sha(after.encode())==NAV_AFTER:
 for edit in reversed(edits): after=after.replace(edit['replacement'],edit['anchor'])
assert sha(after.encode())==entry['after']
before=after
for anchor,replacement in reversed(SOURCE_EDITS[SIDEBAR]):
 assert before.count(replacement)==1
 before=before.replace(replacement,anchor)
assert sha(before.encode())==entry['before']
assert normalize_source(SIDEBAR,before.encode(),entry)==after.encode()
assert normalize_source(SIDEBAR,after.encode(),entry)==after.encode()
combined=after
for edit in edits:
 assert combined.count(edit['anchor'])==1
 combined=combined.replace(edit['anchor'],edit['replacement'])
assert sha(combined.encode())==NAV_AFTER
assert normalize_source(SIDEBAR,combined.encode(),entry)==combined.encode()
def refused(fn):
 try: fn()
 except ValueError: return
 raise AssertionError('Expected evidence refusal')
manifest_data=(HERE/'runtime-evidence/l3-scheduling-4ff499e.json').read_bytes()
refused(lambda: normalize_source(SIDEBAR,combined.encode(),entry,manifest_data+b' '))
changed=json.loads(manifest_data)
changed['targets'][0]['edits'][0]['replacement']+='DRIFT'
refused(lambda: navigation_contract(entry,json.dumps(changed).encode()))
refused(lambda: navigation_contract(dict(entry,after='wrong')))
for token in [\"import { accountBoundary }\",\"accountBoundary.state === 'HYDRATING'\"]:
 assert token in combined
 refused(lambda: normalize_source(SIDEBAR,combined.replace(token,'REMOVED').encode(),entry))
for target,source in actual.items():
 refused(lambda: normalize_source(target,(source+'\\nDRIFT').encode(),manifest[target]))
`, here], { encoding: 'utf8', input: JSON.stringify(sources) })
})
const documentCode = sources['frontend/src/data/document.js']
const communicationScript = sources['frontend/src/components/CommunicationArea.vue'].match(/<script[^>]*>([\s\S]*?)<\/script>/)[1]
const { parse: parseScript } = require('@babel/parser')
let communicationBody = communicationScript
for (const node of parseScript(communicationScript, { sourceType: 'module' }).program.body.filter(node => node.type === 'ImportDeclaration').reverse()) {
  communicationBody = communicationBody.slice(0, node.start) + communicationBody.slice(node.end)
}
const communicationCode = `export function mount(deps) {
const { ref, watch, computed, resumeUnmounted, registerUnsavedEditor, isContentEmpty, usersStore,
useStorage, useWindowSize, useTelemetry, call, createResource, toast, defineProps, defineModel, defineEmits, defineExpose } = deps
${communicationBody}
return { newEmail, newComment, signatureAdded, attachments, showEmailBox, showCommentBox, newEmailEditor, newCommentEditor }
}`
const emailSource = await readFile(resolve(root, 'src/components/EmailEditor.vue'), 'utf8')
const recipientWatchCode = `export function mount(deps) {
const { ref, computed, watch, modelValue, props, toEmails, ccEmails, bccEmails, call } = deps
${emailSource.slice(emailSource.indexOf('const unsubscribedEmails ='), emailSource.indexOf('watch(unsubscribedEmails,'))}
}`

test('all strict transformed JS/TS/JSX and Vue script blocks parse using the fixed Babel parser', () => {
  const { parse } = require('@babel/parser')
  for (const [path, source] of Object.entries(sources)) {
    const script = path.endsWith('.vue') ? source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1] : source
    assert.doesNotThrow(() => parse(script, { sourceType: 'module', plugins: ['typescript', 'jsx'] }), path)
  }
})

async function fixture({ routeName = 'Lead', create = false, communication = false, editors = [], controllers = [] } = {}) {
  const documentOptions = [], toasts = []
  let writeError = null
  let hidden = false, identity = 'Synthetic Sales', covered = true, fail = false
  let readable = true, writable = true, creatable = true, current, session
  const events = {}, requests = [], runtimes = [], config = {}
  const fields = [{ fieldname: 'title', fieldtype: 'Data' }]
  const route = { name: routeName, fullPath: routeName.endsWith('s') ? '/leads?status=New' : '/leads/SYNTHETIC-1#activity',
    hash: '#activity', params: routeName.endsWith('s') ? {} : { leadId: 'SYNTHETIC-1' } }
  let communicationState
  const storageCalls = [], elements = []
  const dom = { querySelector: () => null, querySelectorAll: () => editors, body: { append: x => elements.push(x) }, createElement() {
    return { style: {}, children: [], setAttribute() {}, append(...children) { this.children.push(...children) }, remove() {} }
  } }
  const env = { crypto: webcrypto, cookie: () => 'synthetic-stable', hidden: () => hidden,
    on: (type, fn) => { events[type] = fn }, cover: () => { covered = true }, uncover: () => { covered = false },
    identify: async () => identity, broadcast() {} }
  const context = createContext({ __env: env, Uint32Array, AbortController, Event, console,
    setTimeout, clearTimeout, document: dom, window: { location: {} },
    __: (text, values = []) => text.replace(/\{(\d+)\}/g, (_, index) => values[index]),
  })
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
    if (url === 'frappe.client.set_value') {
      if (writeError) throw writeError
      return { name: 'SYNTHETIC-1', doctype: 'CRM Lead', ...params.fieldname }
    }
    if (url === 'frappe.client.get_doc_permissions') return { permissions: { read: readable, write: writable } }
    if (url === 'frappe.client.has_permission') return { has_permission: params.perm_type === 'create' ? creatable : readable }
    if (url === 'frappe.client.get') return { name: 'SYNTHETIC-1', doctype: 'CRM Lead', title: 'server', email: 'synthetic@example.invalid' }
    if (url === 'crm.api.get_user_signature') return ''
    if (url === 'crm.api.get_unsubscribed_emails') return ['synthetic@example.invalid']
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
    '@/data/script': { getScript: () => ({ setupScript: async () => controllers, scripts: vue.ref([]) }) },
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
    if (communication) {
      const model = vue.computed(() => current.document.doc || {})
      communicationState = modules.get('communication').namespace.mount({ ...vue,
        resumeUnmounted: vue.onUnmounted, registerUnsavedEditor: safe.registerUnsavedEditor,
        isContentEmpty: value => !String(value || '').replace(/<[^>]*>/g, '').trim(),
        usersStore: () => ({ getUser: () => ({ email: 'synthetic@example.invalid' }) }),
        useStorage(key, fallback) {
          storageCalls.push(key)
          assert.equal(key, 'communicationEditorHeight', 'Business draft persistence must not be accessed')
          return vue.ref(fallback)
        },
        useWindowSize: () => ({ height: vue.ref(800) }), useTelemetry: () => ({ capture() {} }),
        call: (url, params) => request({ url, params }),
        createResource: modules.get('resources').namespace.createResource, toast: {},
        defineProps: () => ({ doctype: 'CRM Lead' }), defineModel: name => name === 'reload' ? vue.ref(false) : model,
        defineEmits: () => () => {}, defineExpose() {},
      })
      modules.get('recipientWatch').namespace.mount({ ...vue, modelValue: model, props: { doctype: 'CRM Lead' },
        toEmails: vue.computed(() => model.value.email ? [model.value.email] : []), ccEmails: vue.ref([]), bccEmails: vue.ref([]),
        call: (url, params) => request({ url, params }),
      })
    }
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
        createDocumentResource(options, vm) { documentOptions.push(options); return doc.namespace.createDocumentResource(options, vm) },
        frappeRequest: request, call: (url, params) => request({ url, params }), toast: { error(value) { toasts.push(value) }, success() {} } })
    }
    if (business[id]) return synthetic(id, business[id])
    let code
    if (id === 'document') code = documentCode
    else if (id === 'meta') code = sources['frontend/src/stores/meta.js']
    else if (id === 'communication') code = communicationCode
    else if (id === 'recipientWatch') code = recipientWatchCode
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
  if (communication) { await namespace('communication'); await namespace('recipientWatch') }
  await namespace('main'); await tick(); await vue.nextTick()
  assert.equal(boundary.state, 'ACTIVE'); assert.equal(session.user, 'Synthetic Sales')
  return { boundary, requests, fields, runtimes, namespace, route, storageCalls, documentOptions, toasts,
    writeFailure(value) { writeError = value },
    get communication() { return communicationState },
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


test('actual CommunicationArea setup and EmailEditor immediate recipient watcher recover nonempty-email default activity without persistence', async () => {
  const f = await fixture({ communication: true })
  assert.equal(f.communication.newEmail.value, '')
  assert.equal(f.communication.newComment.value, '')
  assert.equal(f.communication.attachments.value.length, 0)
  assert.deepEqual(f.storageCalls, ['communicationEditorHeight'])
  f.hide(true); await f.resume()
  assert.equal(f.boundary.state, 'ACTIVE'); assert.equal(f.covered, false)
  const calls = f.requests.filter(item => item.url === 'crm.api.get_unsubscribed_emails')
  assert.ok(calls.length >= 2)
  assert.equal(calls.at(-1).params.emails[0], 'synthetic@example.invalid')
  assert.equal(calls.at(-1).params.doctype, 'CRM Lead')
  assert.equal(calls.at(-1).params.name, 'SYNTHETIC-1')
  assert.equal(f.communication.newEmail.value, '')
  assert.ok(f.storageCalls.every(key => key === 'communicationEditorHeight'))
  f.close()
})

test('collapsed mail/comment/attachments register unsaved state and terminal identity clears retained refs; remount never reloads old keys', async () => {
  for (const mode of ['email', 'comment', 'attachments']) {
    const f = await fixture({ communication: true }), previous = f.communication
    if (mode === 'email') previous.newEmail.value = '<p>private unsent email</p>'
    if (mode === 'comment') previous.newComment.value = '<p>private unsent comment</p>'
    if (mode === 'attachments') previous.attachments.value = [{ file_url: '/private/files/synthetic.pdf' }]
    assert.equal(previous.showEmailBox.value, false); assert.equal(previous.showCommentBox.value, false)
    f.hide(true); await f.resume()
    assert.equal(f.boundary.state, 'RETRY_COVERED'); assert.equal(f.covered, true)
    assert.equal(f.communication, previous)
    if (mode === 'attachments') f.boundary.failed({ status: 403 })
    else { f.identity(mode === 'comment' ? 'Guest' : 'Other Account'); await f.boundary.resume() }
    assert.equal(f.boundary.state, 'IDENTITY_REQUIRED')
    assert.equal(previous.newEmail.value, ''); assert.equal(previous.newComment.value, '')
    assert.equal(previous.attachments.value.length, 0)
    const remounted = await fixture({ communication: true })
    assert.equal(remounted.communication.newEmail.value, '')
    assert.equal(remounted.communication.newComment.value, '')
    assert.equal(remounted.communication.attachments.value.length, 0)
    assert.ok(remounted.storageCalls.every(key => key === 'communicationEditorHeight'))
    remounted.close()
  }
})

test('capture checks every contenteditable and explicit draft discard clears retained communication memory', async () => {
  const f = await fixture({ communication: true, editors: [{ textContent: '' }, { textContent: 'second private editor' }] })
  f.hide(true); await f.resume()
  assert.equal(f.boundary.state, 'RETRY_COVERED'); assert.equal(f.covered, true)
  const previous = f.communication
  previous.newEmail.value = 'private'; previous.newComment.value = 'private'
  previous.attachments.value = [{ name: 'synthetic' }]
  ;(await f.namespace('safeResume')).discardResume()
  assert.equal(previous.newEmail.value, ''); assert.equal(previous.newComment.value, '')
  assert.equal(previous.attachments.value.length, 0)
  f.close()
})


test('synchronous document error notification consumes locked/retired hook rejection without weakening epoch guards', async () => {
  let calls = 0
  const f = await fixture({ controllers: [{ _className: 'CRMLead', async onError() { calls++ } }] })
  const old = f.current, notify = f.documentOptions[0].setValue.onError
  f.hide(true)
  assert.equal(notify({ messages: ['Editing this lead is not allowed.'] }), undefined)
  await tick()
  assert.equal(calls, 0)
  assert.deepEqual(f.toasts, ['Editing this lead is not allowed.'])
  await f.resume()
  assert.equal(notify({ messages: [] }), undefined)
  await tick()
  assert.equal(calls, 0)
  assert.equal(f.toasts.at(-1), 'An error occurred while updating the document')
  await assert.rejects(old.triggerOnError(), /locked/)
  f.close()
})

test('active save retains original error promise and server toast while consuming asynchronous onError hook failure', async () => {
  let calls = 0
  const f = await fixture({ controllers: [{ _className: 'CRMLead', async onError() {
    calls++; await tick(); throw Error('Synthetic hook rejection')
  } }] })
  const serverError = { messages: ['Editing this lead is not allowed.'] }
  f.writeFailure(serverError)
  f.current.document.doc.title = 'unsaved'
  const pending = f.current.document.save.submit()
  await assert.rejects(pending, error => error === serverError)
  await tick(); await tick()
  assert.equal(calls, 1)
  assert.equal(f.boundary.state, 'ACTIVE')
  assert.equal(f.toasts[0], 'Editing this lead is not allowed.')
  assert.equal(f.toasts[1], 'An error occurred while running the document script')
  assert.equal(f.current.document.doc.title, 'unsaved')
  const notify = f.documentOptions[0].setValue.onError
  f.toasts.length = 0
  notify({ exc_type: 'MandatoryError', messages: ['Missing: first_name', 'Missing: email'] })
  assert.equal(f.toasts[0], 'Mandatory field error: first_name, email')
  await tick(); await tick()
  f.close()
})

test('an in-flight hook failure after pause is consumed without stale feedback; active normal hooks still execute', async () => {
  let release, calls = 0
  const gate = new Promise(resolve => { release = resolve })
  const f = await fixture({ controllers: [{ _className: 'CRMLead', async onError() {
    calls++; await gate; throw Error('Late synthetic hook failure')
  } }] })
  f.documentOptions[0].setValue.onError({ messages: [] })
  await tick(); assert.equal(calls, 1)
  f.hide(true); release(); await tick(); await tick()
  assert.deepEqual(f.toasts, ['An error occurred while updating the document'])
  f.close()
  let success = 0
  const active = await fixture({ controllers: [{ _className: 'CRMLead', async onError() { success++ } }] })
  active.documentOptions[0].setValue.onError({ messages: ['Synthetic server failure'] })
  await tick()
  assert.equal(success, 1)
  assert.deepEqual(active.toasts, ['Synthetic server failure'])
  active.close()
})


test('automatic load/render/save notifications observe rejected hooks without changing successful resource promise', async () => {
  const calls = []
  const controller = { _className: 'CRMLead' }
  for (const name of ['onLoad', 'onRender', 'onSave']) controller[name] = async () => {
    calls.push(name); await tick(); throw Error('Synthetic automatic hook rejection')
  }
  const f = await fixture({ controllers: [controller] })
  await tick(); await tick()
  assert.deepEqual(calls, ['onLoad', 'onRender'])
  assert.equal(f.toasts.length, 2)
  f.current.document.doc.title = 'explicitly saved'
  const result = await f.current.document.save.submit()
  assert.equal(result.title, 'explicitly saved')
  await tick(); await tick()
  assert.deepEqual(calls, ['onLoad', 'onRender', 'onSave'])
  assert.equal(f.toasts.length, 3)
  assert.ok(f.toasts.every(value => value === 'An error occurred while running the document script'))
  assert.equal(f.boundary.state, 'ACTIVE')
  f.close()
})
