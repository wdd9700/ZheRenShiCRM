import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import { webcrypto } from 'node:crypto'

const tick = () => new Promise(resolve => setImmediate(resolve))
const secret = 'DO-NOT-RECORD-cookie-token-identity-body-stack'

async function bootstrap(options = {}) {
  const nodes = [], attributes = new Map(), listeners = {}, installed = [], requests = []
  let mounts = 0, checks = 0
  function element(tag) {
    const node = { tag, children: [], setAttribute() {}, append(...items) { this.children.push(...items) },
      replaceChildren() { this.children = [] }, remove() { this.removed = true } }
    nodes.push(node); return node
  }
  const document = { cookie: secret, visibilityState: options.hidden ? 'hidden' : 'visible',
    head: element('head'), body: element('body'),
    documentElement: { setAttribute: (k, v) => attributes.set(k, v), removeAttribute: k => attributes.delete(k) },
    createElement: element, getElementById: id => nodes.findLast(n => n.id === id && !n.removed),
    addEventListener(type, fn) { listeners[type] = fn } }
  const window = { crypto: webcrypto, addEventListener(type, fn) { listeners[type] = fn } }
  const crash = stage => { if (options.fail === stage) throw Error(secret) }
  const app = { config: { globalProperties: {} }, use(plugin) { const name = typeof plugin === 'string' ? plugin : 'PINIA_PLUGIN'; installed.push(name); crash(name) },
    component() { crash('COMPONENTS') }, mount() { crash('MOUNT'); mounts++ }, unmount() {} }
  let timeout
  const context = createContext({ document, window, Uint32Array, AbortController,
    setTimeout(fn) { timeout = fn; return 1 }, clearTimeout() {},
    BroadcastChannel: class { postMessage() {} }, location: { reload() {}, assign() {} },
    fetch: async (url, request) => {
      checks++; requests.push({ url, request })
      if (options.identify) return options.identify(request)
      return { ok: true, json: async () => ({ message: secret }) }
    } })
  const boundaryModule = new SourceTextModule(await readFile(new URL('./payload/resources/accountBoundary.js', import.meta.url), 'utf8'), { context })
  await boundaryModule.link(() => { throw Error('Unexpected boundary import') }); await boundaryModule.evaluate()
  const boundary = boundaryModule.namespace.accountBoundary
  const imports = {
    vue: { createApp() { crash('APP_CREATE'); return app }, nextTick: tick },
    pinia: { createPinia() { crash('PINIA_CREATE'); return { state: { value: {} } } }, disposePinia() {} },
    './utils/dialogs': { createDialog() {} }, './socket': { initSocket() { crash('SOCKET'); return {} } },
    './router': { default: 'ROUTER_PLUGIN' }, './translation': { default: 'TRANSLATION_PLUGIN' },
    './App.vue': { default: {} }, './resumeRuntime': { createResumeAdapter: () => ({}) },
    'frappe-ui': { FrappeUI: 'FRAPPE_UI_PLUGIN', Button: {}, TextInput: {}, FormControl: {}, ErrorMessage: {},
      Dialog: {}, Alert: {}, Badge: {}, setConfig() {}, frappeRequest: async () => { crash('DEV_CONTEXT'); return {} } },
    '@framework/ui/telemetry': { telemetryPlugin: 'TELEMETRY_PLUGIN' },
    'frappe-ui/experimental': { spritePlugin: 'SPRITE_PLUGIN' },
  }
  const main = new SourceTextModule((await readFile(new URL('./payload/main.js', import.meta.url), 'utf8'))
    .replaceAll('import.meta.env.DEV', options.dev ? 'true' : 'false'), { context })
  await main.link(specifier => {
    if (specifier.endsWith('/accountBoundary')) return boundaryModule
    const values = specifier === './index.css' ? {} : imports[specifier]
    assert.ok(values, `Unexpected main import ${specifier}`)
    return new SyntheticModule(Object.keys(values), function () {
      for (const [k, v] of Object.entries(values)) this.setExport(k, v)
    }, { context })
  })
  await main.evaluate(); await tick()
  return { boundary, document, attributes, nodes, listeners, installed, requests, timeout: () => timeout(),
    get mounts() { return mounts }, get checks() { return checks }, async settle() { await boundary.resume(); await tick() } }
}

function diagnostic(f, stage, failure) {
  const actual = f.boundary.diagnostic
  assert.equal(actual.version, 'C011100'); assert.equal(actual.stage, stage)
  assert.equal(actual.failureStage, failure === 'NONE' ? 'NONE' : stage)
  assert.equal(actual.failure, failure)
  assert.equal(f.attributes.get('data-crm-first-failure'), failure)
  assert.ok(Object.isFrozen(actual))
  assert.ok(!JSON.stringify([...f.attributes]).includes(secret))
  assert.ok(!f.nodes.filter(n => n.textContent).map(n => n.textContent).join('\n').includes(secret))
  if (failure !== 'NONE') {
    assert.equal(f.attributes.has('data-crm-account-blocked'), true)
    assert.match(f.document.getElementById('crm-initialization-diagnostic').textContent, new RegExp(failure))
    assert.equal(f.mounts, 0)
  }
}

test('M20 actual main stage diagnostics remain successful in production and DEV', async () => {
  for (const dev of [false, true]) {
    const f = await bootstrap({ dev }); diagnostic(f, 'READY', 'NONE')
    assert.equal(f.mounts, 1); assert.equal(f.checks, 1)
    assert.equal(f.requests[0].request.cache, 'no-store')
    assert.equal(f.attributes.has('data-crm-account-blocked'), false)
    assert.deepEqual(f.installed, ['FRAPPE_UI_PLUGIN', 'SPRITE_PLUGIN', 'PINIA_PLUGIN', 'ROUTER_PLUGIN', 'TRANSLATION_PLUGIN', 'TELEMETRY_PLUGIN'])
  }
})

test('M20 initialization failures retain allowlisted first-stage diagnostics, no raw exception', async () => {
  for (const [stage, failure] of [
    ['PINIA_CREATE', 'INITIALIZATION_EXCEPTION'], ['APP_CREATE', 'INITIALIZATION_EXCEPTION'],
    ['FRAPPE_UI_PLUGIN', 'PLUGIN_EXCEPTION'], ['SPRITE_PLUGIN', 'PLUGIN_EXCEPTION'],
    ['PINIA_PLUGIN', 'PLUGIN_EXCEPTION'], ['ROUTER_PLUGIN', 'ROUTER_EXCEPTION'],
    ['TRANSLATION_PLUGIN', 'PLUGIN_EXCEPTION'], ['COMPONENTS', 'INITIALIZATION_EXCEPTION'],
    ['TELEMETRY_PLUGIN', 'PLUGIN_EXCEPTION'], ['SOCKET', 'SOCKET_EXCEPTION'], ['MOUNT', 'MOUNT_EXCEPTION'],
  ]) {
    const f = await bootstrap({ fail: stage }); diagnostic(f, stage, failure)
    assert.equal(f.mounts, 0); assert.equal(f.attributes.has('data-crm-account-blocked'), true)
  }
  diagnostic(await bootstrap({ dev: true, fail: 'DEV_CONTEXT' }), 'DEV_CONTEXT', 'CONTEXT_EXCEPTION')
  diagnostic(await bootstrap({ dev: true, fail: 'SOCKET' }), 'SOCKET', 'SOCKET_EXCEPTION')
})

test('initial hidden waits without identifying or mounting, visible starts normally', async () => {
  const f = await bootstrap({ hidden: true })
  assert.equal(f.checks, 0); assert.equal(f.mounts, 0)
  f.document.visibilityState = 'visible'; f.listeners.visibilitychange()
  await f.settle(); diagnostic(f, 'READY', 'NONE'); assert.equal(f.mounts, 1)
})

test('identity categories remain allowlisted; transient errors expose retry, Guest remains terminal', async () => {
  for (const [identify, failure] of [
    [async () => { throw Error(secret) }, 'IDENTITY_UNAVAILABLE'],
    [async () => ({ ok: false }), 'IDENTITY_HTTP'],
    [async () => ({ ok: true, redirected: true }), 'IDENTITY_REDIRECT'],
    [async () => ({ ok: true, json: async () => { throw Error(secret) } }), 'IDENTITY_RESPONSE'],
    ...['Guest', '', null, {}, 42].map(message => [async () => ({ ok: true, json: async () => ({ message }) }), 'IDENTITY_INVALID']),
  ]) {
    const f = await bootstrap({ identify }); diagnostic(f, 'IDENTITY', failure)
    assert.equal(f.mounts, 0); assert.equal(f.attributes.has('data-crm-account-blocked'), true)
    assert.equal(f.boundary.state, failure === 'IDENTITY_INVALID' ? 'IDENTITY_REQUIRED' : 'RETRY_COVERED')
  }
  const f = await bootstrap({ identify: request => new Promise((_resolve, reject) => {
    request.signal.addEventListener('abort', () => reject(Error(secret)))
  }) })
  f.timeout(); await f.settle(); diagnostic(f, 'IDENTITY', 'IDENTITY_TIMEOUT')
  assert.equal(f.boundary.state, 'RETRY_COVERED')
})

test('cookie changes during identification remain terminal and diagnostics reject arbitrary values', async () => {
  let resolve
  const f = await bootstrap({ identify: () => new Promise(yes => { resolve = yes }) })
  f.document.cookie = 'changed'
  resolve({ ok: true, json: async () => ({ message: secret }) })
  await f.settle(); diagnostic(f, 'IDENTITY', 'SESSION_CHANGED')
  assert.equal(f.boundary.user, null)
  const good = await bootstrap()
  good.boundary.markStage(secret)
  assert.equal(good.boundary.diagnostic.stage, 'READY')
  good.boundary.lock(undefined, secret)
  assert.equal(good.boundary.diagnostic.failure, 'BOUNDARY_LOCK')
  assert.ok(Object.isFrozen(good.boundary.diagnostic))
  assert.ok(!JSON.stringify([...good.attributes]).includes(secret))
})
