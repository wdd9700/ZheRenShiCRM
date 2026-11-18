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
  const { dispose } = init(document, window, { ...options, autoLoad: true, currentUser: 'A@example.test' })
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
  const { dispose: close } = init(document, window, { ...options, currentUser: 'B@example.test' })
  staleList.resolve(jsonResponse({ message: { items: [{ title: 'old private response' }] } }))
  await flush()
  assert.equal($('current-user').textContent, 'B@example.test')
  assert.equal($('schedule-list').textContent, '')
  assert.equal($('schedule-form').listeners.get('submit').length, 1)
  close()
})

const schedule = (name, start, end) => ({
  name, title: name, description: '', owner: 'member@example.test', revision: 4,
  status: 'Active', source_timezone: 'UTC', availability: 'Busy', members: [],
  start_utc: `2026-11-01T09:${start}:00Z`, end_utc: `2026-11-01T09:${end}:00Z`,
})

function resolveUtc(payload) {
  return jsonResponse({ message: { utc: payload.local + ':00Z', timezone: 'UTC', offset_minutes: 0 } })
}

test('adjacent native short blocks meet but do not overlap, and numbers fit their own slots', async () => {
  const items = [schedule('first', '00', '10'), schedule('next', '10', '15')]
  const { document, window } = createDom(page, async (url, options) => {
    if (url.endsWith('.resolve_local')) return resolveUtc(JSON.parse(options.body))
    assert.match(url, /\.list$/)
    return jsonResponse({ message: { items } })
  })
  const { dispose } = init(document, window, { root: document.body, standalone: false })
  document.getElementById('day-date').value = '2026-11-01'
  await fire(document.getElementById('day-form'), 'submit')
  const [first, next] = document.querySelectorAll('.timeline-block')
  assert.equal(first.style.height, '12px')
  assert.equal(next.style.height, '6px')
  assert.equal(first.style.left, next.style.left)
  assert.equal(parseFloat(first.style.top) + parseFloat(first.style.height), parseFloat(next.style.top))
  const markers = document.querySelectorAll('.timeline-marker')
  assert.equal(markers.length, 2)
  assert.deepEqual(markers.map(marker => marker.textContent), ['1', '2'])
  assert.equal(parseFloat(markers[1].style.top) - parseFloat(markers[0].style.top), 28)

  // The DOM stub implements no CSS. Inspect the generated CSS as well as the rendered geometry.
  const css = read('frontend/src/pages/teamSchedule.css')
  const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
  for (const property of ['min-height: 2rem', 'margin: 0.25rem 0.25rem 0.25rem 0']) {
    const rule = rules.find(([, , body]) => body.includes(property))
    assert.ok(rule, property)
    assert.match(rule[1], /button:not\(\.timeline-block, \.timeline-marker\)/)
  }
  assert.match(css, /\.crm-native-schedule \.timeline-block \{[^}]*min-height: 0/)
  assert.match(css, /\.crm-native-schedule \.timeline-marker \{[^}]*height: 24px; min-height: 0; margin: 0; padding: 0/)
  dispose()
})

test('native header protects the edit draft, then creates without touching the old record', async () => {
  const original = schedule('old-id', '00', '10')
  const records = new Map([[original.name, { ...original }]])
  const writes = []
  const { document, window } = createDom(page, async (url, options) => {
    const payload = JSON.parse(options.body)
    if (url.endsWith('.resolve_local')) return resolveUtc(payload)
    if (url.endsWith('.list')) return jsonResponse({ message: { items: [...records.values()] } })
    if (url.endsWith('.get')) return jsonResponse({ message: { schedule: records.get(payload.name) } })
    if (url.endsWith('.query')) return jsonResponse({ message: { busy: [] } })
    const method = url.split('.').at(-1)
    assert.ok(['create', 'update'].includes(method), url)
    writes.push({ method, payload })
    const update = method === 'update'
    const saved = { ...original, ...(update ? payload.changes : payload), name: update ? payload.name : 'new-id', revision: 1 }
    records.set(saved.name, saved)
    return jsonResponse({ message: { schedule: saved } })
  })
  const $ = id => document.getElementById(id)
  // Restore the relevant nesting the DOM stub flattens.
  const title = $('schedule-title')
  title.remove()
  $('editor-section').append(title)
  const script = page.split('<script setup>')[1].split('</script>')[0].replace(/^import .*\n/gm, '')
  let mount, unmount, acceptDiscard = false
  const confirmations = []
  window.confirm = text => { confirmations.push(text); return acceptDiscard }
  const context = { document, window, catalog, init,
    ref: value => ({ value: value === null ? document.body : value }),
    onMounted: callback => { mount = callback }, onBeforeUnmount: callback => { unmount = callback },
    accountBoundary: { state: 'ACTIVE', epoch: 1, user: original.owner, assertActive() {}, onInvalidate: () => () => {} },
  }
  vm.runInNewContext(script, context)
  mount()
  try {
    $('day-date').value = '2026-11-01'
    await fire($('day-form'), 'submit')
    await document.querySelector('.timeline-block').click()
    await $('edit-schedule').click()
    assert.equal($('editing-name').value, 'old-id')
    $('schedule-title').value = 'unsaved edit'
    const headerHandler = page.match(/<Button[^>]*@click="(\w+)"[^>]*>\s*创建日程/)[1]
    context[headerHandler]()
    assert.equal(confirmations.length, 1)
    assert.equal($('schedule-title').value, 'unsaved edit')
    assert.equal($('editing-revision').value, '4')
    assert.equal(writes.length, 0)

    acceptDiscard = true
    context[headerHandler]()
    assert.equal(confirmations.length, 2)
    for (const id of ['editing-name', 'editing-revision', 'schedule-title']) assert.equal($(id).value, '')
    assert.equal($('schedule-submit').textContent, '创建日程')
    assert.equal(document.activeElement, $('schedule-title'))
    $('schedule-title').value = 'new schedule'
    $('schedule-start').value = '2026-11-01T10:00'
    $('schedule-end').value = '2026-11-01T10:05'
    context[headerHandler]()
    assert.equal(confirmations.length, 2)
    assert.equal($('schedule-title').value, 'new schedule')
    await fire($('schedule-form'), 'submit')
    assert.deepEqual(writes.map(write => write.method), ['create'])
    assert.equal(writes[0].payload.title, 'new schedule')
    assert.equal(writes[0].payload.name, undefined)
    assert.equal(writes[0].payload.expected_revision, undefined)
    assert.deepEqual(records.get('old-id'), original)
    assert.equal(records.get('new-id').title, 'new schedule')
  } finally {
    unmount()
  }
})

for (const method of ['create', 'update']) {
  test(`${method} keeps the submitted UTC snapshot when timezone changes during delayed resolution`, async () => {
    const firstResolution = deferred()
    const writeResponse = deferred()
    const resolutions = [], writes = [], busyQueries = []
    const original = schedule('old-id', '00', '10')
    const { document, window } = createDom(page, async (url, options) => {
      const payload = JSON.parse(options.body)
      const endpoint = url.split('.').at(-1)
      if (endpoint === 'resolve_local') {
        resolutions.push(payload)
        return resolutions.length === 1 ? firstResolution.promise : resolveUtc(payload)
      }
      if (endpoint === 'query') {
        busyQueries.push(payload)
        return jsonResponse({ message: { busy: [] } })
      }
      writes.push({ endpoint, payload })
      return writeResponse.promise
    })
    let requestId
    const newUuid = window.crypto.randomUUID
    window.crypto.randomUUID = () => (requestId = newUuid())
    const $ = id => document.getElementById(id)
    const { dispose } = init(document, window, { root: document.body, standalone: false })
    if (method === 'update') {
      $('editing-name').value = original.name
      $('editing-revision').value = String(original.revision)
    } else {
      await $('add-create-member').click()
      $('create-member-rows').querySelector('.member-user').value = 'reader@example.test'
    }
    $('schedule-title').value = 'submitted title'
    $('schedule-description').value = 'submitted description'
    $('schedule-availability').value = 'Free'
    $('schedule-start').value = '2026-11-01T10:00'
    $('schedule-end').value = '2026-11-01T10:05'
    $('schedule-start-offset').value = '0'
    $('schedule-end-offset').value = '0'
    const expectedId = requestId
    const form = $('schedule-form')
    const pending = fire(form, 'submit')
    await flush()
    assert.equal(resolutions.length, 1)
    const lockedAtResolution = form.inert
    // Bypass the user-input lock programmatically to prove the RPC uses one snapshot.
    $('schedule-timezone').value = 'Asia/Shanghai'
    $('schedule-start').value = '2026-11-01T14:00'
    $('schedule-start-offset').value = '480'
    $('schedule-end-offset').value = '480'
    $('schedule-title').value = 'not submitted'
    $('schedule-description').value = 'not submitted'
    $('schedule-availability').value = 'Busy'
    if (method === 'create') $('create-member-rows').querySelector('.member-user').value = 'other@example.test'
    await fire(form, 'input', { target: $('schedule-timezone') })
    firstResolution.resolve(resolveUtc(resolutions[0]))
    for (let i = 0; i < 8 && writes.length === 0; i++) await flush()
    const lockedAtWrite = form.inert
    writeResponse.resolve(jsonResponse({ message: { schedule: original } }))
    await pending
    assert.deepEqual(writes.map(x => x.endpoint), [method])
    const fields = {
      title: 'submitted title', description: 'submitted description', availability: 'Free',
      start_utc: '2026-11-01T10:00:00Z', end_utc: '2026-11-01T10:05:00Z', source_timezone: 'UTC',
    }
    assert.deepEqual(writes[0].payload, method === 'create'
      ? { ...fields, members: [{ user: 'reader@example.test', access: 'Read' }], request_id: expectedId }
      : { name: original.name, expected_revision: original.revision, changes: fields })
    assert.deepEqual(resolutions, ['10:00', '10:05'].map(minute => ({
      local: `2026-11-01T${minute}`, timezone: 'UTC', offset_minutes: 0,
    })))
    assert.deepEqual(busyQueries.map(query => query.display_timezone), ['UTC'])
    assert.equal(lockedAtResolution, true)
    assert.equal(lockedAtWrite, true)
    assert.equal(form.inert, false)
    assert.equal($('schedule-submit').disabled, false)
    dispose()
  })
}

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
