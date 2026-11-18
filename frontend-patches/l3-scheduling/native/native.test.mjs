import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import test from 'node:test'
import vm from 'node:vm'

const root = process.env.S020_APPLIED_ROOT
const req = createRequire(import.meta.url)
const { createDom, fire, flush, deferred, jsonResponse } = req('../../../apps/team_schedule/team_schedule/tests/ui/dom-stub.cjs')
const read = path => readFileSync(join(root, path), 'utf8')
const page = read('frontend/src/pages/TeamSchedule.vue')
const { init } = await import(pathToFileURL(join(root, 'frontend/src/pages/teamScheduleController.mjs')))
const { default: catalog } = await import(pathToFileURL(join(root, 'frontend/src/pages/teamScheduleCatalog.mjs')))

test('router registers a lazy native page, uses the /crm base, and enforces existing CRM and guest gates', async () => {
  let loggedIn = true, isCrmUser = true, options, guard
  const window = { location: {}, innerWidth: 1280 }
  const context = { window, createRouter: input => { options = input; return { beforeEach: fn => { guard = fn } } },
    createWebHistory: base => ({ base }), sessionStore: () => ({ isLoggedIn: loggedIn, user: 'schedule@example.test' }),
    usersStore: () => ({ users: { fetched: true }, isCrmUser: () => isCrmUser, isAdmin: () => false }) }
  vm.runInNewContext(read('frontend/src/router.js').replace(/^import .*\n/gm, '').replace(/^export /gm, '').replace(/^default router.*$/m, ''), context)
  const route = options.routes.find(x => x.name === 'TeamSchedule')
  assert.equal(options.history.base + route.path, '/crm/team-schedule')
  assert.match(String(route.component), /import\('@\/pages\/TeamSchedule\.vue'\)/)
  assert.ok(options.routes.some(x => x.name === 'Leads'))
  assert.ok(options.routes.some(x => x.name === 'Deals'))
  const targets = []
  const go = () => guard({ name: route.name, matched: [route] }, {}, target => targets.push(target?.name || 'proceed'))
  await go()
  isCrmUser = false
  await go()
  loggedIn = false
  await go()
  assert.deepEqual(targets, ['proceed', 'Not Permitted'])
  assert.equal(window.location.href, '/login?redirect-to=%2Fcrm%2Fteam-schedule')
  const sidebar = read('frontend/src/components/Layouts/AppSidebar.vue')
  assert.match(sidebar, /v-if="isCrmUser\(\)"\s+:route="\{ name: 'TeamSchedule' \}"\s+:active="route.name === 'TeamSchedule'"/)
  assert.match(sidebar, /@click="selectItem\(\$event, 'TeamSchedule'\)"/)
  assert.doesNotMatch(sidebar, /href="\/team-schedule"/)
})

test('mounted native DOM uses CRM identity/CSRF, rejects stale responses and removes bindings before re-entry', async () => {
  const requests = []
  const staleList = deferred()
  const { document, window } = createDom(page, async (url, options) => {
    requests.push({ url, options })
    const payload = JSON.parse(options.body)
    if (url.endsWith('.resolve_local')) return jsonResponse({ message: { utc: payload.local + ':00Z', timezone: 'UTC', offset_minutes: 0 } })
    if (url.endsWith('.list')) return staleList.promise
    throw new Error('unexpected request ' + url)
  })
  let active = true, rechecked = 0
  const $ = id => document.getElementById(id)
  const options = { root: document.body, csrfToken: 'crm-csrf', catalog, standalone: false,
    assertSession: () => { if (!active) throw new Error('boundary locked') }, recheck: () => { rechecked++ } }
  const dispose = init(document, window, { ...options, autoLoad: true, currentUser: 'A@example.test' })
  assert.equal($('current-user').textContent, 'A@example.test')
  assert.equal(window.broadcastChannels.length, 0)
  assert.equal(document.listeners.get('visibilitychange'), undefined)
  for (let i = 0; i < 8 && !requests.some(req => req.url.endsWith('.list')); i++) await flush()
  assert.equal(requests.length, 3)
  assert.equal(requests[2].options.headers['X-Frappe-CSRF-Token'], 'crm-csrf')
  assert.equal(requests[2].options.credentials, 'same-origin')
  $('schedule-title').value = 'old draft'; $('viewer-user').value = 'private viewer'; $('ics-file').value = 'example.ics'
  await $('reload-page').click()
  assert.equal(rechecked, 1)
  active = false
  await fire($('schedule-form'), 'submit')
  assert.equal(requests.length, 3)
  dispose(); dispose()
  assert.equal(requests[2].options.signal.aborted, true)
  for (const id of ['current-user', 'schedule-title', 'viewer-user', 'ics-file']) {
    assert.equal(id === 'current-user' ? $(id).textContent : $(id).value, '')
  }
  assert.equal($('schedule-form').listeners.get('submit').length, 0)
  active = true
  const close = init(document, window, { ...options, currentUser: 'B@example.test' })
  staleList.resolve(jsonResponse({ message: { items: [{ title: 'old private response' }] } }))
  await flush()
  assert.equal($('current-user').textContent, 'B@example.test')
  assert.equal($('schedule-list').textContent, '')
  assert.equal($('schedule-form').listeners.get('submit').length, 1)
  close()
})

test('resume captures no schedule drafts, reloads CRM guards before commit, and rejects unavailable permission', async () => {
  const calls = []
  const initial = { name: 'TeamSchedule', fullPath: '/team-schedule' }
  const router = { currentRoute: { value: initial }, isReady: async () => calls.push('router-ready') }
  const browser = { dispatchEvent: event => calls.push(event.type) }
  const context = { window: browser, Event, document: { querySelector: () => null },
    captureResume: () => assert.fail('schedule must not be captured as a Lead/Deal draft'),
    accountBoundary: { state: 'ACTIVE', readRevision: 0, hydrate: () => calls.push('hydrate') } }
  vm.runInNewContext(read('frontend/src/resumeRuntime.js').replace(/^import .*\n/gm, '').replace(/^export /gm, '') + '\ncreate = createResumeAdapter', context)
  const adapter = context.create({ router, boot: async () => calls.push('boot'), stop: () => calls.push('unmount'),
    nextTick: async () => {}, read: () => assert.fail('must not issue schedule API reads during hydration') })
  adapter.suspend()
  const recovery = { assertCurrent: () => calls.push('current'), settleReads: async () => calls.push('guards') }
  const callbacks = await adapter.refresh(recovery)
  assert.deepEqual(calls, ['unmount', 'hydrate', 'boot', 'router-ready', 'guards', 'current'])
  callbacks.commit(); callbacks.afterCommit()
  assert.equal(calls.at(-1), 'crm-team-schedule-active')
  router.currentRoute.value = { name: 'Not Permitted', fullPath: '/not-permitted' }
  await assert.rejects(adapter.refresh(recovery), { status: 403 })
})
