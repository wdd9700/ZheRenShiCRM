import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import { webcrypto } from 'node:crypto'

const tick = () => new Promise(resolve => setImmediate(resolve))
function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
async function fixture(identify = async () => 'Synthetic Sales') {
  let hidden = false, cookie = 'synthetic-cookie', uncovered = 0, identities = 0
  const events = {}, covers = [], config = {}
  const env = { crypto: webcrypto, cookie: () => cookie, hidden: () => hidden,
    on(type, fn) { events[type] = fn }, cover: (...args) => covers.push(args), uncover: () => uncovered++,
    identify: () => { identities++; return identify() }, broadcast() {} }
  const context = createContext({ __env: env, Uint32Array, AbortController, Event, console, setTimeout, clearTimeout })
  const modules = new Map()
  function synthetic(id, values) {
    if (!modules.has(id)) modules.set(id, new SyntheticModule(Object.keys(values), function () {
      for (const [k, v] of Object.entries(values)) this.setExport(k, v)
    }, { context }))
    return modules.get(id)
  }
  async function load(id) {
    if (modules.has(id)) return modules.get(id)
    if (id === 'vue') return synthetic(id, { reactive: x => x, watch() {}, effectScope: () => ({ run: fn => fn(), stop() {} }) })
    if (id === 'config') return synthetic(id, { getConfig: key => config[key] })
    if (id === 'debounce') return synthetic(id, { default: fn => fn })
    if (id === 'request') return synthetic(id, { request: options => config.resourceFetcher(options) })
    if (id === 'realtime') return synthetic(id, { onDocUpdate() {} })
    if (id === 'socketAccess') return synthetic(id, { readSocket() {} })
    const path = ['safeResume', 'resumeRuntime'].includes(id) ? `./payload/${id}.js` : `./payload/resources/${id}.${id === 'local' ? 'ts' : 'js'}`
    let code = await readFile(new URL(path, import.meta.url), 'utf8')
    if (id === 'local') code = code.replace(/<T = any>/g, '').replace(/: Promise<(?:T \| null|null)>/g, '').replace(/: string/g, '').replace(/: T/g, '')
    if (id === 'accountBoundary') code = code.replace('createAccountBoundary(browserEnvironment())', 'createAccountBoundary(globalThis.__env)')
    const mod = new SourceTextModule(code, { context, identifier: id })
    modules.set(id, mod); return mod
  }
  async function namespace(id) {
    const mod = await load(id)
    if (mod.status === 'unlinked') await mod.link(spec => load(spec.split('/').at(-1)))
    if (mod.status !== 'evaluated') await mod.evaluate()
    return mod.namespace
  }
  const boundary = (await namespace('accountBoundary')).accountBoundary
  await boundary.resume()
  return { boundary, events, covers, config, env, namespace, setIdentify(fn) { identify = fn },
    get uncovered() { return uncovered }, get identities() { return identities },
    hide(value) { hidden = value; events.visibilitychange() }, cookie(value) { cookie = value } }
}
function adapter(f, refresh = async () => ({ commit() {} })) {
  let captures = 0, discards = 0
  f.boundary.setAdapter({ suspend() { captures++ }, discard() { discards++ }, refresh })
  return { get captures() { return captures }, get discards() { return discards } }
}

test('hidden-visible recovery is one flight, fresh read then second identity then atomic reveal', async () => {
  const f = await fixture(), fresh = deferred(), order = []
  const a = adapter(f, async context => { order.push('fresh'); await fresh.promise; context.assertCurrent(); return { commit() { order.push('commit') } } })
  f.hide(true); assert.equal(f.boundary.state, 'SUSPENDED'); assert.equal(a.captures, 1)
  assert.throws(() => f.boundary.assertActive())
  f.hide(false); const one = f.boundary.resume(), two = f.boundary.resume()
  assert.equal(one, two); await tick()
  assert.equal(f.uncovered, 1); assert.equal(f.identities, 2)
  fresh.resolve(); await one
  assert.equal(f.identities, 3); assert.deepEqual(order, ['fresh', 'commit'])
  assert.equal(f.boundary.state, 'ACTIVE'); assert.equal(f.uncovered, 2)
  assert.equal(f.boundary.diagnostic.failure, 'PAGE_HIDDEN')
})

test('hide again while recovering invalidates first recovery and never commits it', async () => {
  const f = await fixture(), first = deferred()
  let calls = 0, commits = 0
  adapter(f, async context => { if (++calls === 1) await first.promise; context.assertCurrent(); return { commit() { commits++ } } })
  f.hide(true); f.hide(false); const old = f.boundary.resume(); await tick()
  f.hide(true); f.hide(false); await f.boundary.resume()
  first.resolve(); await old
  assert.equal(commits, 1); assert.equal(f.uncovered, 2)
})

test('hidden during initial identity starts fresh on visible; old identity cannot initialize', async () => {
  const before = deferred(), after = deferred()
  const f = await fixture(async () => 'Synthetic Sales')
  f.setIdentify(() => before.promise); adapter(f)
  f.hide(true); f.hide(false); const stale = f.boundary.resume(); await tick()
  f.hide(true); f.setIdentify(() => after.promise); f.hide(false); const current = f.boundary.resume()
  after.resolve('Synthetic Sales'); await current
  before.resolve('Other Account'); await stale
  assert.equal(f.boundary.user, 'Synthetic Sales'); assert.equal(f.boundary.state, 'ACTIVE')
})

test('network failure stays covered, explicit retry works, and BFCache uses same barrier', async () => {
  const f = await fixture(); let refreshes = 0
  adapter(f, async () => { refreshes++; return { commit() {} } })
  f.hide(true); f.setIdentify(async () => { throw Error('offline') }); f.hide(false)
  await f.boundary.resume(); assert.equal(f.boundary.state, 'RETRY_COVERED'); assert.equal(refreshes, 0)
  assert.equal(typeof f.covers.at(-1)[2], 'function')
  f.setIdentify(async () => 'Synthetic Sales'); await f.covers.at(-1)[2]()
  assert.equal(f.boundary.state, 'ACTIVE')
  f.events.pageshow({ persisted: true }); await f.boundary.resume()
  assert.equal(refreshes, 2)
})

test('changed identity, Guest, logout broadcast, cookie change all keep business and drafts inaccessible', async () => {
  for (const mode of ['Other Account', 'Guest', 'broadcast', 'cookie']) {
    const f = await fixture(); let refreshed = 0
    const a = adapter(f, async () => { refreshed++; return { commit() {} } })
    if (mode === 'broadcast') f.events['account-change']()
    else if (mode === 'cookie') { f.cookie('changed'); f.events.focus() }
    else { f.hide(true); f.setIdentify(async () => mode); f.hide(false); await f.boundary.resume() }
    assert.equal(f.boundary.state, 'IDENTITY_REQUIRED'); assert.equal(f.uncovered, 1)
    assert.equal(refreshed, 0); assert.equal(a.discards, 1)
  }
})

test('old read success/error and pending write cannot transform, update new epoch, or replay', async () => {
  for (const result of ['success', 'error', 'write']) {
    const f = await fixture(), old = deferred()
    const { createResource, getCachedResource } = await f.namespace('resources')
    let transforms = 0, successes = 0, errors = 0, writes = 0
    f.config.resourceFetcher = options => { if (options.url === 'frappe.client.set_value') writes++; return old.promise }
    const resource = createResource({ url: result === 'write' ? 'frappe.client.set_value' : 'crm.api.doc.get_data', cache: 'current',
      transform(data) { transforms++; return data }, onSuccess() { successes++ }, onError() { errors++ } })
    const pending = resource.submit(); await tick()
    adapter(f); f.hide(true); f.hide(false); await f.boundary.resume()
    const fresh = createResource({ url: 'crm.api.doc.get_data', cache: 'current' })
    f.config.resourceFetcher = async () => ({ name: 'fresh' }); await fresh.fetch()
    if (result === 'error') old.reject(Error('old error')); else old.resolve({ name: 'old' })
    await assert.rejects(pending, /superseded/)
    assert.equal(transforms, 0); assert.equal(successes, 0); assert.equal(errors, 0)
    assert.equal(writes, result === 'write' ? 1 : 0)
    assert.equal(getCachedResource('current'), fresh); assert.equal(fresh.data.name, 'fresh')
    await assert.rejects(resource.fetch(), /locked/)
  }
})

test('recovery permits explicitly read-only endpoints, not method GET disguises or arbitrary reloads', async () => {
  const f = await fixture(); const { createResource } = await f.namespace('resources')
  let calls = 0
  f.config.resourceFetcher = async () => { calls++; return {} }
  adapter(f, async context => {
    await createResource({ url: 'crm.api.doc.get_data' }).fetch()
    await assert.rejects(createResource({ url: 'frappe.client.set_value', method: 'GET' }).fetch(), /undeclared recovery request/)
    await context.settleReads()
    return { commit() {} }
  })
  f.hide(true); f.hide(false); await f.boundary.resume()
  assert.equal(calls, 1); assert.equal(f.boundary.state, 'RETRY_COVERED')
})

async function draftFixture({ create = false } = {}) {
  const f = await fixture(), draft = await f.namespace('safeResume')
  const fields = [{ fieldname: 'title', fieldtype: 'Data' }, { fieldname: 'secret', fieldtype: 'Data' }]
  let permission = { permissions: { read: 1, write: 1, create: 1 } }
  const name = create ? '' : 'SYNTHETIC-1'
  const original = { title: 'server', secret: 'base' }, document = { doc: { ...original }, originalDoc: { ...original } }
  let dispose = draft.registerResumeDocument('CRM Lead', name, document, () => fields, () => permission)
  draft.registerResumePage(create ? 'Leads' : 'Lead', () => ({ doctype: 'CRM Lead', filters: { status: 'New' } }))
  document.doc.title = 'unsubmitted'; document.doc.secret = 'private draft'
  const snapshot = draft.captureResume({ name: create ? 'Leads' : 'Lead', hash: '#data', fullPath: create ? '/leads' : '/leads/SYNTHETIC-1#data' })
  dispose(); adapter(f); f.hide(true); f.hide(false); await f.boundary.resume()
  const fresh = { doc: { ...original }, originalDoc: { ...original } }
  draft.registerResumeDocument('CRM Lead', name, fresh, () => fields, () => permission)
  return { ...f, draft, fields, fresh, snapshot, setPermission(value) { permission = value } }
}

test('draft is separate from fresh data and restoration is explicit without any network submission', async () => {
  const f = await draftFixture()
  assert.equal(f.fresh.doc.title, 'server')
  const [plan] = f.draft.planDrafts(f.boundary.user)
  assert.equal(plan.values.title, 'unsubmitted'); assert.equal(plan.conflict, false)
  assert.equal(f.draft.restoreDraft(plan), true); assert.equal(f.fresh.doc.title, 'unsubmitted')
  assert.equal(f.draft.planDrafts(f.boundary.user).length, 0)
})

test('revoked read/write/create/field permission and other identity never reveal old draft values', async () => {
  for (const kind of ['read', 'write', 'fields', 'identity', 'create']) {
    const f = await draftFixture({ create: kind === 'create' })
    if (kind === 'fields') f.fields.forEach(field => { field.hidden = 1 })
    else if (kind !== 'identity') f.setPermission({ permissions: { read: 1, write: 1, create: 1, [kind]: 0 } })
    assert.equal(f.draft.planDrafts(kind === 'identity' ? 'Other Account' : f.boundary.user).length, 0)
  }
})

test('server conflict is reported without automatic overwrite; lost rights are checked again at restore', async () => {
  const f = await draftFixture(); f.fresh.doc.title = 'changed on server'
  const [plan] = f.draft.planDrafts(f.boundary.user)
  assert.equal(plan.conflict, true); assert.equal(f.draft.restoreDraft(plan), false)
  assert.equal(f.fresh.doc.title, 'changed on server')
  f.fresh.doc.title = 'server'; const [permitted] = f.draft.planDrafts(f.boundary.user)
  f.setPermission({ permissions: { read: 1, write: 0 } })
  assert.equal(f.draft.restoreDraft(permitted), false); assert.equal(f.fresh.doc.title, 'server')
})

test('creation draft requires current create rights and unsupported editors fail closed', async () => {
  const f = await draftFixture({ create: true })
  assert.equal(f.draft.reopenCreation('CRM Lead'), true)
  assert.equal(f.draft.planDrafts(f.boundary.user).length, 1)
  f.draft.registerResumePage('Lead')
  assert.equal(f.draft.captureResume({ name: 'Lead', hash: '#activity', fullPath: '/leads/SYNTHETIC-1#activity' }).name, 'Lead')
  assert.throws(() => f.draft.captureResume({ name: 'Note', hash: '#emails' }), /当前编辑器/)
  f.draft.discardResume(); assert.equal(f.draft.planDrafts(f.boundary.user).length, 0)
})
