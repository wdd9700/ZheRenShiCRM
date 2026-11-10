import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import { webcrypto } from 'node:crypto'

const base = new URL('./payload/resources/', import.meta.url)

async function fixture(identity = 'Sales A', identify, waitForIdentity = true, readFailureDiagnostics = false) {
  let cookie = 'user_id=misleading-cookie'
  let hidden = false
  const listeners = {}
  const covers = []
  let uncovered = 0
  let broadcasts = 0
  const config = {}
  const env = {
    crypto: webcrypto, cookie: () => cookie, hidden: () => hidden,
    cover: (...args) => covers.push(args), uncover: () => uncovered++,
    on: (type, fn) => { listeners[type] = fn },
    broadcast: () => broadcasts++, identify: identify || (async () => identity), readFailureDiagnostics,
  }
  const context = createContext({ __env: env, console, Event, AbortController, Uint32Array, setTimeout, clearTimeout })
  const cache = new Map()
  function synthetic(id, values) {
    if (!cache.has(id)) cache.set(id, new SyntheticModule(Object.keys(values), function () {
      for (const [key, value] of Object.entries(values)) this.setExport(key, value)
    }, { context, identifier: id }))
    return cache.get(id)
  }
  async function module(id) {
    if (cache.has(id)) return cache.get(id)
    if (id === 'vue') return synthetic(id, {
      reactive: x => x, watch() {}, effectScope: () => ({ run: fn => fn() }),
    })
    if (id.endsWith('/config')) return synthetic(id, { getConfig: key => config[key] })
    if (id.endsWith('/debounce')) return synthetic(id, { default: fn => fn })
    if (id.endsWith('/request')) return synthetic(id, { request: options => config.resourceFetcher(options) })
    if (id.endsWith('/realtime')) return synthetic(id, { onDocUpdate() {} })
    if (id.endsWith('/socketAccess')) return synthetic(id, { readSocket() {} })
    const name = id.split('/').at(-1)
    let code = await readFile(new URL(name + (name === 'local' ? '.ts' : '.js'), base), 'utf8')
    if (name === 'local') code = code.replace(/<T = any>/g, '').replace(/: Promise<(?:T \| null|null)>/g, '').replace(/: string/g, '').replace(/: T/g, '')
    if (name === 'accountBoundary') code = code.replace('createAccountBoundary(browserEnvironment())', 'createAccountBoundary(globalThis.__env)')
    const out = new SourceTextModule(code, { context, identifier: id })
    cache.set(id, out)
    return out
  }
  const root = await module('entry/resources')
  await root.link((specifier) => module(specifier === 'vue' ? 'vue' : 'entry/' + specifier.replace(/^.*\//, '')))
  await root.evaluate()
  const boundary = cache.get('entry/accountBoundary').namespace.accountBoundary
  if (waitForIdentity) await boundary.resume()
  return {
    resources: root.namespace, boundary, config, env, covers, listeners,
    get uncovered() { return uncovered }, get broadcasts() { return broadcasts },
    cookie(value) { cookie = value }, hidden(value) { hidden = value; listeners.visibilitychange() },
    async load(name) {
      const mod = await module('entry/' + name)
      if (mod.status === 'unlinked') await mod.link((specifier) => module(specifier === 'vue' ? 'vue' : 'entry/' + specifier.replace(/^.*\//, '')))
      if (mod.status !== 'evaluated') await mod.evaluate()
      return mod.namespace
    },
  }
}

test('server identity, not editable cookie, gates startup; Guest and offline remain covered', async () => {
  const a = await fixture()
  assert.equal(a.boundary.user, 'Sales A')
  assert.equal(a.uncovered, 1)
  for (const f of [await fixture('Guest'), await fixture(null, async () => { throw Error('offline') })]) {
    assert.equal(f.uncovered, 0)
    assert.throws(() => f.boundary.assertActive(), /locked|superseded/)
  }
})

test('normal resource list/detail success and in-page cache remain functional', async () => {
  const f = await fixture()
  f.config.resourceFetcher = async () => [{ name: 'SYNTH-A' }]
  const r = f.resources.createResource({ url: 'crm.api.doc.get_data', cache: ['Lead'] })
  await r.fetch()
  assert.equal(r.data[0].name, 'SYNTH-A')
  assert.equal(f.resources.getCachedResource(['Lead']), r)
  const documents = await f.load('documentResource')
  f.config.resourceFetcher = async () => ({ name: 'SYNTH-A', doctype: 'CRM Lead', title: 'Synthetic' })
  const doc = documents.createDocumentResource({ doctype: 'CRM Lead', name: 'SYNTH-A', auto: false })
  await doc.reload()
  assert.equal(doc.doc.title, 'Synthetic')
  f.config.resourceFetcher = async () => { throw Object.assign(Error('deleted'), { status: 404, exc_type: 'DoesNotExistError' }) }
  await assert.rejects(doc.reload(), /deleted/)
  assert.equal(doc.doc, null)
  f.boundary.assertActive()
})

test('persistent adapter never accesses preseeded IDB or deletes preferences', async () => {
  const f = await fixture()
  const local = await f.load('local')
  assert.equal(await local.getLocal('old-admin-records'), null)
  assert.equal(await local.saveLocal('records', { private: true }), null)
  assert.equal(await local.deleteLocal('preferences'), null)
  assert.doesNotMatch(await readFile(new URL('local.ts', base), 'utf8'), /indexedDB|idb-keyval|localStorage/)
})

test('ordinary request error does not restore previous sensitive generic data', async () => {
  const f = await fixture()
  const r = f.resources.createResource({ url: 'custom.read', cache: ['custom'] })
  f.config.resourceFetcher = async () => ({ synthetic: 'A only' })
  await r.fetch()
  f.config.resourceFetcher = async () => { throw Error('offline') }
  await assert.rejects(r.fetch(), /offline/)
  assert.equal(r.data, null)
  assert.equal(r.previousData, null)
})

test('same-account revoked permission clears generic data and locks page', async () => {
  const f = await fixture()
  const r = f.resources.createResource({ url: 'crm.api.doc.get_data' })
  r.setData({ rows: ['old-private-record'] })
  f.config.resourceFetcher = async () => { throw Object.assign(Error('denied'), { status: 403 }) }
  await assert.rejects(r.fetch(), /denied/)
  assert.equal(r.data, null)
  assert.throws(() => f.boundary.assertActive(), /locked|superseded/)
  assert.match(f.covers.at(-1)[0], /未保存编辑/)
})

test('active sensitive read failure classification distinguishes native abort, explicit abort, transport and callback failures', async () => {
  for (const kind of ['native-abort', 'explicit-abort', 'transport', 'timeout', 'callback']) {
    const f = await fixture()
    const failure = kind === 'native-abort' ? new DOMException('Synthetic abort', 'AbortError')
      : kind === 'timeout' ? new DOMException('Synthetic timeout', 'TimeoutError')
      : kind === 'transport' ? new TypeError('Synthetic transport failure')
      : new Error('Synthetic failure')
    let rejectPending, started
    const begin = new Promise(resolve => { started = resolve })
    f.config.resourceFetcher = kind === 'explicit-abort'
      ? ({ signal }) => new Promise((resolve, reject) => {
        rejectPending = reject
        signal.addEventListener('abort', () => reject(failure), { once: true })
        started()
      })
      : async () => { if (kind !== 'callback') throw failure; return { rows: [] } }
    const r = f.resources.createResource({
      url: 'crm.api.doc.get_data',
      onSuccess() { if (kind === 'callback') throw failure },
    })
    const pending = r.fetch()
    if (kind === 'explicit-abort') { await begin; r.abort(); assert.ok(rejectPending) }
    const aborted = kind === 'native-abort' || kind === 'explicit-abort'
    await assert.rejects(pending, error => aborted ? error.name === 'AbortError' : error === failure)
    assert.equal(f.boundary.state, aborted ? 'ACTIVE' : 'IDENTITY_REQUIRED', kind)
    assert.equal(f.boundary.diagnostic.failure, aborted ? 'NONE' : 'ACCESS_UNCONFIRMED', kind)
  }
})

test('list failure clears originalData, rows, and lookup map', async () => {
  const f = await fixture()
  const { createListResource } = await f.load('listResource')
  const list = createListResource({ doctype: 'CRM Lead' })
  f.config.resourceFetcher = async () => [{ name: 'SYNTH-A' }]
  await list.list.fetch()
  assert.equal(list.getRow('SYNTH-A').name, 'SYNTH-A')
  f.config.resourceFetcher = async () => { throw Error('offline') }
  await assert.rejects(list.list.fetch(), /offline/)
  assert.equal(list.data, null)
  assert.equal(list.originalData, null)
  assert.equal(Object.keys(list.dataMap).length, 0)
})

test('identity switch never shares cache, pending old response never calls success', async () => {
  const a = await fixture('Administrator')
  const b = await fixture('Sales A')
  assert.notEqual(a.resources.getCacheKey('Lead'), b.resources.getCacheKey('Lead'))
  let resolve
  let successes = 0
  a.config.resourceFetcher = () => new Promise(r => { resolve = r })
  const r = a.resources.createResource({ url: 'crm.api.doc.get_data', onSuccess: () => successes++ })
  const pending = r.fetch()
  await Promise.resolve()
  a.cookie('user_id=Sales A')
  resolve({ rows: ['administrator-only'] })
  await assert.rejects(pending, /locked|superseded/)
  assert.equal(r.data, null)
  assert.equal(successes, 0)
  assert.equal(b.resources.getCachedResource('Lead'), null)
})

test('background, BFCache and multi-tab changes cover without automatic draft deletion', async () => {
  for (const action of [f => f.hidden(true), f => f.listeners.pageshow({ persisted: true }), f => f.listeners['account-change']()]) {
    const f = await fixture()
    const draft = { text: 'unsubmitted synthetic draft' }
    action(f)
    assert.throws(() => f.boundary.assertActive(), /locked|superseded/)
    assert.equal(draft.text, 'unsubmitted synthetic draft')
    assert.equal(f.uncovered, 1)
  }
})

test('login/logout remain callable while covered and changed broadcasts', async () => {
  const f = await fixture()
  f.boundary.lock()
  f.config.resourceFetcher = async () => 'Logged Out'
  const logout = f.resources.createResource({ url: 'logout' })
  assert.equal(await logout.submit(), 'Logged Out')
  f.boundary.changed()
  assert.equal(f.broadcasts, 1)
})

test('identity changes during async validation prevent network submission', async () => {
  const f = await fixture()
  let calls = 0
  f.config.resourceFetcher = async () => { calls++; return {} }
  const r = f.resources.createResource({ url: 'frappe.client.set_value', validate: async () => {
    f.cookie('user_id=Other Account')
  } })
  await assert.rejects(r.submit(), /locked|superseded/)
  assert.equal(calls, 0)
})

test('document save failure retains unsubmitted local draft without restoring server snapshot', async () => {
  const f = await fixture()
  const { createDocumentResource } = await f.load('documentResource')
  const doc = createDocumentResource({ doctype: 'CRM Lead', name: 'SYNTH-A', auto: false })
  f.config.resourceFetcher = async () => ({ name: 'SYNTH-A', title: 'Saved' })
  await doc.reload()
  doc.doc.title = 'Unsaved synthetic draft'
  f.config.resourceFetcher = async () => { throw Object.assign(Error('Invalid field'), { status: 417, exc_type: 'ValidationError' }) }
  await assert.rejects(doc.save.submit(), /Invalid field/)
  assert.equal(doc.doc.title, 'Unsaved synthetic draft')
  f.boundary.assertActive()
})

test('browser adapter uses no-store service identity, persistent cover, and native logout escape', async () => {
  const nodes = []
  const attributes = new Map()
  function element(tag) {
    const node = { tag, children: [], setAttribute() {}, append(...items) { this.children.push(...items) },
      replaceChildren() { this.children = [] }, remove() { this.removed = true } }
    nodes.push(node)
    return node
  }
  const requests = []
  let target
  const document = {
    cookie: 'user_id=not-trusted', visibilityState: 'visible', head: element('head'), body: element('body'),
    documentElement: { setAttribute: (k, v) => attributes.set(k, v), removeAttribute: k => attributes.delete(k) },
    createElement: element, getElementById: id => nodes.find(n => n.id === id && !n.removed), addEventListener() {},
  }
  let broadcast = 0
  const window = { crypto: webcrypto, csrf_token: 'synthetic-csrf', addEventListener() {} }
  const location = { assign: value => { target = value }, reload() {} }
  const context = createContext({ document, window, location, Uint32Array, AbortController, setTimeout, clearTimeout,
    BroadcastChannel: class { postMessage() { broadcast++ } },
    fetch: async (url, options) => {
      requests.push({ url, options })
      return { ok: true, redirected: false, json: async () => ({ message: 'Server Sales A' }) }
    },
  })
  const code = await readFile(new URL('accountBoundary.js', base), 'utf8')
  const mod = new SourceTextModule(code, { context })
  await mod.link(() => { throw Error('unexpected import') })
  await mod.evaluate()
  const boundary = mod.namespace.accountBoundary
  await boundary.ready
  assert.equal(boundary.user, 'Server Sales A')
  assert.equal(requests[0].url, '/api/method/frappe.auth.get_logged_user')
  assert.equal(requests[0].options.cache, 'no-store')
  assert.equal(requests[0].options.credentials, 'same-origin')
  assert.equal(attributes.has('data-crm-account-blocked'), false)
  boundary.lock()
  assert.equal(attributes.has('data-crm-account-blocked'), true)
  const logout = document.getElementById('crm-account-boundary').children.find(n => n.textContent?.startsWith('退出当前登录'))
  await logout.onclick()
  assert.equal(requests[1].url, '/api/method/logout')
  assert.equal(requests[1].options.headers['X-Frappe-CSRF-Token'], 'synthetic-csrf')
  assert.equal(broadcast, 1)
  assert.equal(target, '/login?redirect-to=/crm')
})

test('actual CRM session callbacks use confirmed identity and full navigation for login/logout', async () => {
  async function session(f) {
    const location = { assign(value) { this.href = value } }
    const context = createContext({ window: { location } })
    const code = await readFile(new URL('./payload/session.js', import.meta.url), 'utf8')
    const mod = new SourceTextModule(code, { context })
    await mod.link(async specifier => {
      const values = specifier === 'pinia' ? { defineStore: (_name, setup) => setup }
        : specifier === 'vue' ? { ref: value => ({ value }), computed: fn => ({ get value() { return fn() } }) }
        : specifier === 'frappe-ui' ? { createResource: f.resources.createResource }
        : { accountBoundary: f.boundary }
      return new SyntheticModule(Object.keys(values), function () {
        for (const [key, value] of Object.entries(values)) this.setExport(key, value)
      }, { context })
    })
    await mod.evaluate()
    return { store: mod.namespace.sessionStore(), location }
  }
  const admin = await fixture('Administrator')
  const a = await session(admin)
  assert.equal(a.store.user.value, 'Administrator')
  admin.config.resourceFetcher = async () => { admin.cookie('user_id=Guest'); return 'Logged Out' }
  await a.store.logout.submit()
  assert.equal(a.store.user.value, null)
  assert.equal(a.location.href, '/login?redirect-to=/crm')
  assert.equal(admin.broadcasts, 1)
  const sales = await fixture('Sales A')
  const b = await session(sales)
  assert.equal(b.store.user.value, 'Sales A')
  sales.config.resourceFetcher = async () => ({ message: 'Logged In' })
  await b.store.login.submit()
  assert.equal(b.location.href, '/crm')
  assert.throws(() => sales.boundary.assertActive(), /locked|superseded/)
})

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

const tick = () => new Promise(resolve => setImmediate(resolve))
const salesUser = { name: 'Sales A', email: 'sales-a@example.invalid', role: 'Sales User' }

async function routerConsumers(f) {
  const { createHash } = await import('node:crypto')
  const hashes = {
    router: '5978786c44b5a79a506e8316aa8f2c3db844d558d575b02bfbc6da76f4db9f6b',
    users: '9e2b275acbb20a495168b3c1b22f4dbf1f48b7acb9c86f6f8b6770a96d46009d',
    views: 'cd7967d37f0e5dccab8a89019c258a5554248b33860be60708c038fb178e553a',
  }
  let guard
  const context = createContext({
    console: { error() {} }, window: { innerWidth: 1440, location: {} },
    localStorage: { getItem: () => null }, requestIdleCallback() {}, queueMicrotask,
  })
  const modules = new Map()
  function synthetic(id, values) {
    if (!modules.has(id)) modules.set(id, new SyntheticModule(Object.keys(values), function () {
      for (const [key, value] of Object.entries(values)) this.setExport(key, value)
    }, { context, identifier: id }))
    return modules.get(id)
  }
  async function load(id) {
    if (modules.has(id)) return modules.get(id)
    if (id === 'vue') return synthetic(id, {
      reactive: x => x, ref: value => ({ value }), computed: fn => ({ get value() { return fn() } }),
    })
    if (id === 'pinia') return synthetic(id, { defineStore: (_name, setup) => {
      let store
      return () => store ||= setup()
    } })
    if (id === 'vue-router') return synthetic(id, {
      createWebHistory: () => ({}), createRouter: () => ({ beforeEach(fn) { guard = fn } }),
    })
    if (id === 'frappe-ui') return synthetic(id, {
      createResource: f.resources.createResource, call: () => { throw Error('Unexpected direct call') },
    })
    if (id.endsWith('/session')) return synthetic('session', { sessionStore: () => ({ get user() { return f.boundary.user }, isLoggedIn: true }) })
    const name = id.split('/').at(-1)
    const code = await readFile(new URL('./consumer-fixtures/' + name + '.js', import.meta.url), 'utf8')
    assert.equal(createHash('sha256').update(code).digest('hex'), hashes[name], 'Fixed consumer fixture drift')
    const mod = new SourceTextModule(code, { context, identifier: name })
    modules.set(name, mod)
    return mod
  }
  const router = await load('router')
  await router.link(load)
  await router.evaluate()
  return {
    guard: (...args) => guard(...args),
    users: () => modules.get('users').namespace.usersStore(),
    views: () => modules.get('views').namespace.viewsStore(),
  }
}

const deepLink = () => ({ name: 'Lead', params: { leadId: 'SYNTH-A' }, hash: '#activity', matched: [{}], query: {} })

test('fixed router preserves Sales deep link while delayed get_users is pending', async () => {
  const f = await fixture()
  const response = deferred()
  f.config.resourceFetcher = () => response.promise
  const app = await routerConsumers(f)
  const next = []
  const target = deepLink()
  const navigating = app.guard(target, {}, value => next.push(value))
  const users = app.users().users
  const published = users.promise
  assert.equal(typeof published?.then, 'function')
  await tick()
  assert.equal(users.promise, published)
  assert.equal(users.fetched, false)
  assert.equal(next.length, 0)
  response.resolve([[salesUser], [salesUser]])
  await published
  assert.equal(users.data.crmUsers[0].name, 'Sales A')
  assert.equal(users.fetched, true)
  await navigating
  assert.equal(next.length, 1)
  assert.equal(next[0], undefined)
  assert.equal(target.params.leadId, 'SYNTH-A')
  assert.equal(target.hash, '#activity')
})

test('fixed router waits delayed get_views for Home and per-route default custom view', async () => {
  for (const name of ['Home', 'Deals']) {
    const f = await fixture()
    const response = deferred()
    f.config.resourceFetcher = options => options.url === 'crm.api.session.get_users'
      ? Promise.resolve([[salesUser], [salesUser]]) : response.promise
    const app = await routerConsumers(f)
    const next = []
    const navigating = app.guard({ name, matched: [{}], params: {}, query: {} }, {}, value => next.push(value))
    await tick()
    const views = app.views().views
    const published = views.promise
    assert.equal(typeof published?.then, 'function')
    assert.equal(views.fetched, false)
    assert.equal(next.length, 0)
    response.resolve([{ name: 'SYNTH-Deal-Board', route_name: 'Deals', dt: 'CRM Deal', type: 'kanban', is_default: 1 }])
    await published
    assert.equal(views.promise, published)
    await navigating
    assert.equal(next.length, 1)
    assert.equal(next[0].name, 'Deals')
    assert.equal(next[0].params.viewType, 'kanban')
    assert.equal(next[0].query.view, 'SYNTH-Deal-Board')
  }
})

test('fixed router awaits identity gate and rejects Guest/offline without requests or private data', async () => {
  for (const failure of ['Guest', 'offline']) {
    const identity = deferred()
    const f = await fixture('Sales A', () => identity.promise, false)
    let calls = 0
    f.config.resourceFetcher = async () => { calls++; return [[salesUser], [salesUser]] }
    const app = await routerConsumers(f)
    const next = []
    const navigating = app.guard(deepLink(), {}, value => next.push(value))
    const users = app.users().users
    assert.equal(typeof users.promise?.then, 'function')
    await tick()
    assert.equal(calls, 0)
    assert.equal(next.length, 0)
    if (failure === 'Guest') identity.resolve('Guest')
    else {
      identity.reject(Error('offline identity'))
      await tick()
      assert.equal(f.boundary.state, 'RETRY_COVERED')
      assert.equal(calls, 0)
      assert.equal(next.length, 0)
      f.boundary.lock('Explicitly abandon startup for this test')
    }
    await assert.rejects(users.promise, /locked|superseded/)
    await navigating
    assert.equal(next.length, 1)
    assert.equal(next[0], false)
    assert.equal(calls, 0)
    assert.equal(users.data, null)
    assert.equal(f.uncovered, 0)
  }
  const f = await fixture()
  f.config.resourceFetcher = async () => { throw Error('offline get_users') }
  const app = await routerConsumers(f)
  const next = []
  await app.guard(deepLink(), {}, value => next.push(value))
  assert.equal(next[0], false)
  assert.equal(app.users().users.data, null)

  const viewsFixture = await fixture()
  viewsFixture.config.resourceFetcher = async options => {
    if (options.url === 'crm.api.session.get_users') return [[salesUser], [salesUser]]
    throw Error('offline get_views')
  }
  const viewsApp = await routerConsumers(viewsFixture)
  const viewsNext = []
  await assert.rejects(viewsApp.guard({ name: 'Home', matched: [{}] }, {}, value => viewsNext.push(value)), /offline get_views/)
  assert.equal(viewsNext.length, 0)
  assert.equal(viewsApp.views().views.data, null)

  const identity = deferred()
  const confirmed = await fixture('Sales A', () => identity.promise, false)
  let calls = 0
  confirmed.config.resourceFetcher = async () => { calls++; return [[salesUser], [salesUser]] }
  const confirmedApp = await routerConsumers(confirmed)
  const confirmedNext = []
  const navigation = confirmedApp.guard(deepLink(), {}, value => confirmedNext.push(value))
  await tick()
  assert.equal(calls, 0)
  assert.equal(confirmedNext.length, 0)
  identity.resolve('Sales A')
  await navigation
  assert.equal(calls, 1)
  assert.equal(confirmedNext.length, 1)
  assert.equal(confirmedNext[0], undefined)
})

test('published promise includes processing; concurrent and callback reentry cannot restore old results', async () => {
  const f = await fixture()
  const pending = []
  f.config.resourceFetcher = () => {
    const request = deferred()
    pending.push(request)
    return request.promise
  }
  const r = f.resources.createResource({ url: 'custom.read', auto: true, transform: data => ({ processed: data }) })
  const first = r.promise
  assert.equal(typeof first?.then, 'function')
  await tick()
  const second = r.fetch()
  assert.equal(r.promise, second)
  await tick()
  pending[1].resolve('current')
  await second
  assert.equal(r.data.processed, 'current')
  pending[0].resolve('obsolete')
  await assert.rejects(first, { name: 'AbortError' })
  assert.equal(r.data.processed, 'current')
  assert.equal(r.promise, second)
  assert.equal(r.loading, false)

  let reentered
  const callbacks = []
  const reentrant = f.resources.createResource({ url: 'custom.read', onSuccess(data) {
    callbacks.push(data)
    if (data === 'one') reentered = reentrant.fetch()
  }, onData(data) { callbacks.push('onData:' + data) } })
  const previous = reentrant.fetch()
  await tick()
  pending[2].resolve('one')
  await assert.rejects(previous, { name: 'AbortError' })
  await tick()
  assert.equal(reentrant.promise, reentered)
  assert.equal(reentrant.loading, true)
  pending[3].resolve('two')
  await reentered
  assert.equal(reentrant.data, 'two')
  assert.deepEqual(callbacks, ['one', 'two', 'onData:two'])

  const obsolete = r.fetch()
  await tick()
  const current = r.fetch()
  await tick()
  pending[5].resolve('fresh')
  await current
  pending[4].reject(Object.assign(Error('obsolete denied'), { status: 403 }))
  await assert.rejects(obsolete, { name: 'AbortError' })
  assert.equal(r.data.processed, 'fresh')
  assert.equal(r.error, null)
  f.boundary.assertActive()

  const cancelled = r.fetch()
  await tick()
  r.abort()
  pending[6].resolve('cancelled result')
  await assert.rejects(cancelled, { name: 'AbortError' })
  assert.equal(r.data.processed, 'fresh')
  assert.equal(r.loading, false)
})

test('same-cache automatic read consumers share pending work without superseding it', async () => {
  const f = await fixture()
  const gate = deferred()
  let calls = 0
  f.config.resourceFetcher = () => { calls++; return gate.promise }
  const options = { url: 'frappe.onboarding.get_onboarding_status', cache: 'onboarding_status', auto: true }
  const first = f.resources.createResource(options)
  const pending = first.promise
  const second = f.resources.createResource({ ...options })
  assert.equal(second, first)
  assert.equal(second.promise, pending)
  await tick()
  assert.equal(calls, 1)
  gate.resolve({ steps: [] })
  await pending
  assert.equal(first.fetched, true)
  f.boundary.assertActive()
})

test('automatic reads with different params do not reuse another consumer request', async () => {
  const f = await fixture()
  const calls = []
  f.config.resourceFetcher = async ({ params }) => { calls.push(params); return params }
  const options = { url: 'frappe.client.get', cache: 'shared', auto: true }
  const first = f.resources.createResource({ ...options, params: { name: 'A' } })
  const second = f.resources.createResource({ ...options, params: { name: 'B' } })
  await Promise.all([first.promise, second.promise])
  assert.notEqual(first, second)
  assert.equal(first.data.name, 'A')
  assert.equal(second.data.name, 'B')
  assert.equal(calls.length, 2)
})

test('automatic sharing compares parameter data and isolates pending old epochs', async () => {
  const f = await fixture()
  const gate = deferred()
  let calls = 0, successes = 0
  f.config.resourceFetcher = () => { calls++; return gate.promise }
  const options = { url: 'frappe.client.get', cache: 'parameters', auto: true, onSuccess: () => successes++ }
  const first = f.resources.createResource({ ...options, params: { doctype: 'CRM Lead', name: 'A' } })
  const pending = first.promise
  const second = f.resources.createResource({ ...options, params: { name: 'A', doctype: 'CRM Lead' } })
  assert.equal(second.promise, pending)
  await tick()
  assert.equal(calls, 1)
  f.hidden(true)
  gate.resolve({ private: 'obsolete' })
  await assert.rejects(pending, { name: 'AbortError' })
  assert.equal(first.data, null)
  assert.equal(successes, 0)
})

test('automatic sharing preserves original fetcher params and rejects lossy or effectful data', async () => {
  let effects = 0
  const cyclic = {}; cyclic.self = cyclic
  const getter = Object.defineProperty({}, 'v', { enumerable: true, get() { effects++; return null } })
  const custom = { toJSON() { effects++; return 'encoded' } }
  const date = new Date('2026-01-01T00:00:00.000Z')
  const symbolKey = { [Symbol('hidden')]: true }
  const hidden = Object.defineProperty({}, 'v', { value: 1 })
  const cases = [
    [{ v: NaN }, { v: null }], [{ v: Infinity }, { v: null }],
    [{ v: -Infinity }, { v: null }], [{ v: -0 }, { v: 0 }],
    [{ v: date }, { v: date.toISOString() }],
    [{ v: [undefined] }, { v: [null] }], [{ v: Array(1) }, { v: [null] }],
    [{ v: undefined }, {}], [{ v: custom }, { v: 'encoded' }],
    [new (class Params { constructor() { this.v = 1 } })(), { v: 1 }],
    [cyclic, cyclic], [{ v() {} }, { v() {} }],
    [{ v: Symbol('value') }, {}], [{ v: 1n }, { v: '1' }],
    [getter, { v: null }], [symbolKey, {}], [hidden, {}],
  ]
  for (const [left, right] of cases) {
    const f = await fixture()
    const calls = []
    const resourceFetcher = async ({ params }) => { calls.push(params); return params === left ? 'left' : 'right' }
    const options = { url: 'frappe.client.get', cache: 'raw-params', auto: true, resourceFetcher }
    const first = f.resources.createResource({ ...options, params: left })
    const second = f.resources.createResource({ ...options, params: right })
    await Promise.all([first.promise, second.promise])
    assert.notEqual(first, second)
    assert.equal(calls.length, 2)
    assert.equal(calls[0], left)
    assert.equal(calls[1], right)
    assert.equal(first.data, 'left')
    assert.equal(second.data, left === right ? 'left' : 'right')
    assert.equal(effects, 0, 'Parameter comparison must not invoke getters or toJSON')
  }
})

test('automatic sharing keeps plain JSON types distinct and accepts nested key order', async () => {
  const f = await fixture()
  const calls = []
  const resourceFetcher = async ({ params }) => { calls.push(params); return params }
  const options = { url: 'frappe.client.get', cache: 'json-types', auto: true, resourceFetcher }
  const resources = [null, false, 0, '0', { v: null }, { v: false }, { v: 0 }, { v: '0' }]
    .map(params => f.resources.createResource({ ...options, params }))
  await Promise.all(resources.map(resource => resource.promise))
  assert.equal(new Set(resources).size, resources.length)
  assert.equal(calls.length, resources.length)
  const first = f.resources.createResource({ ...options, params: { b: [1, { y: true, x: null }], a: 'value' } })
  const second = f.resources.createResource({ ...options, params: { a: 'value', b: [1, { x: null, y: true }] } })
  assert.equal(second.promise, first.promise)
  await first.promise
})

test('same-cache automatic failure remains observable and can retry', async () => {
  const f = await fixture()
  const options = { url: 'frappe.onboarding.get_onboarding_status', cache: 'retry', auto: true }
  f.config.resourceFetcher = async () => { throw Error('network offline') }
  const first = f.resources.createResource(options)
  await assert.rejects(first.promise, /network offline/)
  assert.equal(first.fetched, false)
  f.config.resourceFetcher = async () => []
  const retry = f.resources.createResource({ ...options })
  await retry.promise
  assert.equal(retry.fetched, true)
  const previous = retry
  f.hidden(true)
  const fresh = f.resources.createResource({ ...options, auto: false })
  assert.notEqual(fresh, previous)
  assert.equal(fresh.data, null)
  assert.equal(previous.data, null)
})

test('automatic write requests and force/reload/submit are not coalesced', async () => {
  for (const action of ['write', 'force', 'reload', 'submit']) {
    const url = action === 'write' ? 'frappe.client.insert' : 'frappe.onboarding.get_onboarding_status'
    const f = await fixture()
    const gates = []
    f.config.resourceFetcher = () => { const gate = deferred(); gates.push(gate); return gate.promise }
    const options = { url, cache: 'explicit', auto: true }
    const resource = f.resources.createResource(options)
    const first = resource.promise
    await tick()
    if (action === 'write' || action === 'force') f.resources.createResource({ ...options, force: action === 'force' })
    else resource[action]()
    const current = resource.promise
    assert.notEqual(current, first)
    await tick()
    assert.equal(gates.length, 2)
    gates[1].resolve('current')
    await current
    gates[0].resolve('old')
    await assert.rejects(first, { name: 'AbortError' })
    assert.equal(resource.data, 'current')
  }
})

test('ignored auto rejection is handled but published promise still rejects for consumers', async () => {
  for (const failure of ['network', 'transform', 'onSuccess']) {
    const f = await fixture()
    const fail = () => { throw Error('controlled auto failure: ' + failure) }
    f.config.resourceFetcher = failure === 'network' ? fail : async () => 'response'
    const r = f.resources.createResource({
      url: 'custom.read', auto: true, ...(failure === 'network' ? {} : { [failure]: fail }),
    })
    const published = r.promise
    await tick()
    await tick()
    assert.equal(r.promise, published)
    await assert.rejects(published, /controlled auto failure/)
    assert.equal(r.error.message, 'controlled auto failure: ' + failure)
    assert.equal(r.data, null)
  }
})


test('temporary diagnostic retired resource late fetch is not current and cannot mislabel a later sensitive failure', async () => {
  const f = await fixture('Sales A', undefined, true, true)
  let transports = 0
  const failure = new TypeError('Synthetic current transport failure')
  f.config.resourceFetcher = async () => { transports++; throw failure }
  const retired = f.resources.createResource({ url: 'frappe.desk.search.search_link' })
  const auth = f.resources.createResource({ url: 'login' })
  const originalEpoch = f.boundary.epoch
  f.boundary.setAdapter({ async refresh() { return { commit() {} } } })
  f.boundary.pause()
  await f.boundary.resume()
  assert.equal(f.boundary.state, 'ACTIVE')
  assert.ok(f.boundary.epoch > originalEpoch)
  await assert.rejects(retired.fetch(), error => error.name === 'AbortError')
  assert.equal(transports, 0)
  assert.equal(f.boundary.state, 'ACTIVE')
  const firstCode = f.boundary.diagnostic.readFailureCode
  assert.equal(firstCode.split('/')[1], 'PREPARE')
  assert.equal(firstCode.split('/')[2], 'AbortError')
  assert.equal(firstCode.split('/')[6], '0')
  const current = f.resources.createResource({ url: 'crm.api.doc.get_data' })
  await assert.rejects(current.fetch(), error => error === failure)
  assert.equal(transports, 1)
  assert.equal(f.boundary.state, 'IDENTITY_REQUIRED')
  assert.match(f.covers.at(-1)[0], /请求失败，无法确认当前数据访问权限/)
  assert.equal(f.boundary.diagnostic.failure, 'PAGE_HIDDEN')
  assert.equal(f.boundary.diagnostic.readFailureCode, firstCode)
  await assert.rejects(auth.fetch(), error => error === failure)
  assert.equal(transports, 2)

  const a = await fixture('Sales A', undefined, true, true)
  const login = a.resources.createResource({ url: 'login' })
  a.boundary.setAdapter({ async refresh() { return { commit() {} } } })
  a.boundary.pause()
  await a.boundary.resume()
  a.config.resourceFetcher = async () => { throw failure }
  await assert.rejects(login.fetch(), error => error === failure)
  assert.equal(a.boundary.state, 'ACTIVE')
  assert.equal(a.boundary.diagnostic.readFailureCode.split('/')[6], '1')
})
