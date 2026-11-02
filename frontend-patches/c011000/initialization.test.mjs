import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { SourceTextModule, SyntheticModule, createContext } from 'node:vm'
import { webcrypto } from 'node:crypto'

const tick = () => new Promise(resolve => setImmediate(resolve))
const secret = 'DO-NOT-RECORD-cookie-token-identity-body-stack'

async function bootstrap(options = {}) {
  const nodes = []
  const attributes = new Map()
  const listeners = {}
  const requests = []
  const installed = []
  let mounts = 0
  function element(tag) {
    const node = { tag, children: [], setAttribute() {}, append(...items) { this.children.push(...items) },
      replaceChildren() { this.children = [] }, remove() { this.removed = true } }
    nodes.push(node)
    return node
  }
  const document = {
    cookie: secret, visibilityState: 'visible', head: element('head'), body: element('body'),
    documentElement: { setAttribute: (key, value) => attributes.set(key, value), removeAttribute: key => attributes.delete(key) },
    createElement: element, getElementById: id => nodes.findLast(node => node.id === id && !node.removed),
    addEventListener(type, fn) { listeners[type] = fn },
  }
  const window = { crypto: webcrypto, addEventListener(type, fn) { listeners[type] = fn } }
  const crash = stage => { if (options.fail === stage) throw Error(secret) }
  const app = {
    config: { globalProperties: {} },
    use(plugin) { installed.push(plugin); crash(plugin); return this },
    component() { crash('COMPONENTS') },
    mount() { crash('MOUNT'); mounts++ },
  }
  let timeout
  const context = createContext({ document, window, Uint32Array, AbortController,
    setTimeout(fn) { timeout = fn; return 1 }, clearTimeout() {},
    BroadcastChannel: class { postMessage() {} }, location: { reload() {}, assign() {} },
    fetch: async (url, request) => {
      requests.push({ url, request })
      if (options.identify) return options.identify(request)
      return { ok: true, redirected: false, json: async () => ({ message: secret }) }
    },
  })
  const boundaryCode = await readFile(new URL('./payload/resources/accountBoundary.js', import.meta.url), 'utf8')
  const boundaryModule = new SourceTextModule(boundaryCode, { context })
  await boundaryModule.link(() => { throw Error('Unexpected boundary import') })
  await boundaryModule.evaluate()
  const boundary = boundaryModule.namespace.accountBoundary
  const imports = {
    vue: { createApp() { crash('APP_CREATE'); return app } },
    pinia: { createPinia() { crash('PINIA_CREATE'); return 'PINIA_PLUGIN' } },
    './utils/dialogs': { createDialog() {} },
    './socket': { initSocket() { crash('SOCKET'); return {} } },
    './router': { default: 'ROUTER_PLUGIN' }, './translation': { default: 'TRANSLATION_PLUGIN' },
    './App.vue': { default: {} },
    'frappe-ui': { FrappeUI: 'FRAPPE_UI_PLUGIN', Button: {}, TextInput: {}, FormControl: {},
      ErrorMessage: {}, Dialog: {}, Alert: {}, Badge: {}, setConfig() {},
      frappeRequest: async () => { crash('DEV_CONTEXT'); return {} } },
    '@framework/ui/telemetry': { telemetryPlugin: 'TELEMETRY_PLUGIN' },
    'frappe-ui/experimental': { spritePlugin: 'SPRITE_PLUGIN' },
  }
  const mainCode = (await readFile(new URL('./payload/main.js', import.meta.url), 'utf8'))
    .replaceAll('import.meta.env.DEV', options.dev ? 'true' : 'false')
  const main = new SourceTextModule(mainCode, { context })
  await main.link(specifier => {
    if (specifier.endsWith('/accountBoundary')) return boundaryModule
    const values = specifier === './index.css' ? {} : imports[specifier]
    assert.ok(values, `Unexpected main import ${specifier}`)
    return new SyntheticModule(Object.keys(values), function () {
      for (const [key, value] of Object.entries(values)) this.setExport(key, value)
    }, { context })
  })
  await main.evaluate()
  await tick()
  return { boundary, document, attributes, nodes, listeners, requests, installed, timeout: () => timeout(),
    get mounts() { return mounts }, async settle() { await boundary.ready; await tick() } }
}

function diagnostic(fixture, stage, failure) {
  const actual = fixture.boundary.diagnostic
  assert.equal(actual.version, 'C011100')
  assert.equal(actual.stage, stage)
  assert.equal(actual.failureStage, failure === 'NONE' ? 'NONE' : stage)
  assert.equal(actual.failure, failure)
  assert.equal(fixture.attributes.get('data-crm-first-failure'), failure)
  const visible = fixture.nodes.filter(node => node.textContent).map(node => node.textContent).join('\n')
  assert.ok(!JSON.stringify([...fixture.attributes]).includes(secret))
  assert.ok(!visible.includes(secret))
  if (failure !== 'NONE') {
    assert.equal(fixture.attributes.has('data-crm-account-blocked'), true)
    assert.match(fixture.document.getElementById('crm-initialization-diagnostic').textContent, new RegExp(failure))
    assert.equal(fixture.mounts, 0)
  }
}

test('actual main bootstrap succeeds in production and DEV with local stage only', async () => {
  for (const dev of [false, true]) {
    const f = await bootstrap({ dev })
    diagnostic(f, 'READY', 'NONE')
    assert.equal(f.mounts, 1)
    assert.equal(f.requests.length, 1)
    assert.equal(f.requests[0].request.cache, 'no-store')
    assert.equal(f.attributes.has('data-crm-account-blocked'), false)
    assert.deepEqual(f.installed, ['FRAPPE_UI_PLUGIN', 'SPRITE_PLUGIN', 'PINIA_PLUGIN', 'ROUTER_PLUGIN', 'TRANSLATION_PLUGIN', 'TELEMETRY_PLUGIN'])
  }
})

test('actual main classifies synchronous plugin/router/socket/mount errors without recording exceptions', async () => {
  for (const [stage, failure] of [
    ['PINIA_CREATE', 'INITIALIZATION_EXCEPTION'], ['APP_CREATE', 'INITIALIZATION_EXCEPTION'],
    ['FRAPPE_UI_PLUGIN', 'PLUGIN_EXCEPTION'], ['SPRITE_PLUGIN', 'PLUGIN_EXCEPTION'],
    ['PINIA_PLUGIN', 'PLUGIN_EXCEPTION'], ['ROUTER_PLUGIN', 'ROUTER_EXCEPTION'],
    ['TRANSLATION_PLUGIN', 'PLUGIN_EXCEPTION'], ['COMPONENTS', 'INITIALIZATION_EXCEPTION'],
    ['TELEMETRY_PLUGIN', 'PLUGIN_EXCEPTION'], ['SOCKET', 'SOCKET_EXCEPTION'], ['MOUNT', 'MOUNT_EXCEPTION'],
  ]) diagnostic(await bootstrap({ fail: stage }), stage, failure)
  diagnostic(await bootstrap({ dev: true, fail: 'DEV_CONTEXT' }), 'DEV_CONTEXT', 'CONTEXT_EXCEPTION')
  diagnostic(await bootstrap({ dev: true, fail: 'SOCKET' }), 'SOCKET', 'SOCKET_EXCEPTION')
})

test('browser identity categories are allowlisted, fail closed, and survive main catch', async () => {
  for (const [identify, code] of [
    [async () => { throw Error(secret) }, 'IDENTITY_UNAVAILABLE'],
    [async () => ({ ok: false, redirected: false }), 'IDENTITY_HTTP'],
    [async () => ({ ok: true, redirected: true }), 'IDENTITY_REDIRECT'],
    [async () => ({ ok: true, json: async () => { throw Error(secret) } }), 'IDENTITY_RESPONSE'],
    ...['Guest', '', null, {}, 42].map(message => [async () => ({ ok: true, json: async () => ({ message }) }), 'IDENTITY_INVALID']),
  ]) {
    const f = await bootstrap({ identify })
    diagnostic(f, 'IDENTITY', code)
    assert.equal(f.installed.length, 0)
    assert.match(f.document.getElementById('crm-account-boundary').children[0].textContent, /无法确认服务端登录身份/)
  }
  const f = await bootstrap({ identify: request => new Promise((resolve, reject) => {
    request.signal.addEventListener('abort', () => reject(Error(secret)))
  }) })
  f.timeout()
  await f.settle()
  diagnostic(f, 'IDENTITY', 'IDENTITY_TIMEOUT')
})

test('hidden while identifying remains first reason after visible and successful identity; no automatic unlock', async () => {
  let resolve
  const f = await bootstrap({ identify: () => new Promise(yes => { resolve = yes }) })
  f.document.visibilityState = 'hidden'
  f.listeners.visibilitychange()
  f.document.visibilityState = 'visible'
  f.listeners.visibilitychange()
  resolve({ ok: true, json: async () => ({ message: secret }) })
  await f.settle()
  diagnostic(f, 'IDENTITY', 'PAGE_HIDDEN')
  assert.equal(f.boundary.user, null)
  assert.match(f.document.getElementById('crm-account-boundary').children[0].textContent, /标签曾进入后台/)
  f.boundary.markStage(secret)
  f.boundary.initializationFailed()
  f.boundary.lock(secret, secret)
  diagnostic(f, 'IDENTITY', 'PAGE_HIDDEN')
})

test('session changes and initial hidden state retain allowlisted identity-stage failure', async () => {
  for (const mode of ['cookie', 'hidden']) {
    let resolve
    const f = await bootstrap({ identify: () => new Promise(yes => { resolve = yes }) })
    if (mode === 'cookie') f.document.cookie = 'changed'
    else f.document.visibilityState = 'hidden'
    resolve({ ok: true, json: async () => ({ message: secret }) })
    await f.settle()
    diagnostic(f, 'IDENTITY', mode === 'cookie' ? 'SESSION_CHANGED' : 'PAGE_HIDDEN')
  }
})

test('invalid stage/failure inputs cannot enter diagnostic fields', async () => {
  const f = await bootstrap()
  f.boundary.markStage(secret)
  assert.equal(f.boundary.diagnostic.stage, 'READY')
  f.boundary.lock(undefined, secret)
  assert.equal(f.boundary.diagnostic.failure, 'BOUNDARY_LOCK')
  assert.ok(Object.isFrozen(f.boundary.diagnostic))
  assert.ok(!JSON.stringify([...f.attributes]).includes(secret))
})
