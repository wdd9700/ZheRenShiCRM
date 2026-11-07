const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.join(__dirname, 'team_access/public/page.js'), 'utf8')
const template = fs.readFileSync(path.join(__dirname, 'team_access/www/team-activities.html'), 'utf8')
const rootId = template.match(/<section id="([^"]+)" data-csrf=/)[1]
const secret = 'SYNTHETIC-SECRET-NOT-FOR-STATUS'
const cases = [
  { code: 400, category: '请求格式错误' },
  { code: 401, category: '身份认证失败' },
  { code: 403, category: '访问或会话校验被拒绝' },
  { code: 417, category: '输入或业务校验失败' },
  { code: 500, category: '服务器处理异常' },
  { code: 200, exc: true, category: '服务端响应异常' },
  { code: 500, nonJson: true, category: '响应格式或传输异常' },
  { code: 200, nonJson: true, category: '响应格式或传输异常' },
  { code: 200, lostBody: true, category: '响应格式或传输异常' },
  { offline: true, category: '网络或连接异常' },
  { lostResponse: true, category: '网络或连接异常' },
  { code: 200, invalid: null, category: '服务端响应异常' },
  { code: 200, invalid: {}, category: '保存确认响应不完整' },
  { code: 200, invalid: { message: { name: 'synthetic-result', doctype: 'Wrong Type' } }, category: '保存确认响应不完整' },
]

async function run(user, doctype, savedName = doctype === 'CRM Task' ? 3 : 'synthetic-result') {
  const elements = new Map()
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, { value: '', disabled: false, hidden: false, textContent: '', children: [], replaceChildren() { this.children = [] }, append(child) { this.children.push(child) }, querySelector: () => element('submit') })
    return elements.get(id)
  }
  element(rootId).dataset = { user, csrf: secret }
  const websiteWrapper = { dataset: {} }
  const getElementById = (id) => id === 'page-team-activities' ? websiteWrapper : element(id)
  element('activity-type').value = doctype
  const calls = []
  const writes = []
  let rows = []
  let creates = 0
  let updates = 0
  let scenario = { code: 200 }
  const fetch = async (url, options = {}) => {
    if (options.method !== 'POST') return { ok: true, json: async () => ({ message: rows }) }
    calls.push({ url, options })
    if (scenario.offline) throw new Error(secret)
    const document = JSON.parse(options.body).document
    if (scenario.lostResponse || scenario.lostBody || scenario.code >= 400) writes.push(document)
    if (scenario.lostResponse) throw new Error(secret)
    return {
      status: scenario.code,
      ok: scenario.code >= 200 && scenario.code < 300,
      json: async () => {
        if (scenario.nonJson) throw new SyntaxError(secret)
        if (scenario.lostBody) throw new Error(secret)
        if (Object.hasOwn(scenario, 'invalid')) return scenario.invalid
        if (Object.hasOwn(scenario, 'invalidName')) return { message: { doctype, name: scenario.invalidName } }
        if (scenario.code >= 400 || scenario.exc) return { exc: secret, exc_type: secret, message: secret, _server_messages: secret, traceback: secret, token: secret }
        const saved = { ...document, name: savedName, owner: user }
        if (Object.hasOwn(document, 'name')) {
          assert.equal(document.name, savedName)
          assert.equal(rows.length, 1)
          updates++
        } else creates++
        rows = [saved]
        return { message: saved }
      },
    }
  }
  vm.runInNewContext(source, { document: { getElementById, createElement: () => element(Symbol()) }, fetch, URLSearchParams, window: { confirm: () => true } })
  await new Promise((resolve) => setImmediate(resolve))
  const submit = async (editing = false) => {
    if (!editing) element('activity-new').onclick()
    element('activity-title').value = secret
    element('activity-content').value = `合成 <b>content</b>, comma ${secret}`
    element('activity-parent-type').value = user === 'a' ? '' : 'CRM Lead'
    element('activity-parent').value = user === 'a' ? '' : 'synthetic-parent'
    const before = calls.length
    await element('activity-form').onsubmit({ preventDefault() {} })
    assert.equal(calls.length, before + 1)
    const { url, options } = calls.at(-1)
    assert.equal(url, '/api/method/team_access.api.save_activity')
    assert.equal(options.credentials, 'same-origin')
    assert.equal(options.cache, 'no-store')
    assert.equal(options.headers['Content-Type'], 'application/json')
    assert.equal(options.headers['X-Frappe-CSRF-Token'], secret)
    const payload = JSON.parse(options.body)
    assert.deepEqual(Object.keys(payload), ['document'])
    if (editing) assert.equal(payload.document.name, savedName)
    else assert.ok(!Object.hasOwn(payload.document, 'name'))
    assert.equal(payload.document.doctype, doctype)
    assert.equal(payload.document.title, secret)
    assert.equal(payload.document.custom_team_visibility, 'Private')
    assert.equal(payload.document.custom_team_collaborator, '')
    assert.equal(payload.document.reference_doctype, user === 'a' ? '' : 'CRM Lead')
    assert.equal(payload.document.reference_docname, user === 'a' ? '' : 'synthetic-parent')
    assert.equal(payload.document[doctype === 'FCRM Note' ? 'content' : 'description'], `合成 <b>content</b>, comma ${secret}`)
    return element('activity-status').textContent
  }
  assert.match(await submit(), /保存成功/)
  assert.equal(String(element('activity-name').value), String(savedName))
  assert.equal(element('submit').disabled, false)
  element('activity-new').onclick()
  assert.equal(element('activity-title').value, '')
  await element('activity-refresh').onclick()
  assert.equal(element('activity-list').children.length, 1)
  element('activity-list').children[0].children[0].onclick()
  assert.equal(String(element('activity-name').value), String(savedName))
  assert.equal(element('activity-title').value, secret)
  assert.equal(element('activity-content').value, `合成 <b>content</b>, comma ${secret}`)
  assert.equal(element('activity-visibility').value, 'Private')
  assert.equal(element('activity-parent').value, user === 'a' ? '' : 'synthetic-parent')
  assert.match(await submit(true), /保存成功/)
  assert.equal(creates, 1)
  assert.equal(updates, 1)
  assert.equal(rows.length, 1)
  const invalidNames = [null, true, false, {}, [], 3.5, 0, -3, Number.MAX_SAFE_INTEGER + 1, '']
  if (doctype === 'FCRM Note') invalidNames.push(3)
  for (scenario of [...cases, ...invalidNames.map((invalidName) => ({ code: 200, invalidName, category: '保存确认响应不完整' }))]) {
    const text = await submit()
    assert.ok(text.startsWith(scenario.category))
    assert.ok(text.includes('保存结果未确认'))
    assert.ok(text.includes('只读回查'))
    assert.ok(text.includes('勿盲目重复提交'))
    assert.ok(!text.includes(secret))
    assert.ok(!text.includes('未保存'))
    assert.ok(!text.includes('保存成功'))
    if (scenario.code) assert.ok(text.includes(`HTTP ${scenario.code}`))
  }
  assert.ok(writes.length > 0)
}

;(async () => {
  for (const user of ['a', 'Administrator']) {
    for (const doctype of ['FCRM Note', 'CRM Task']) await run(user, doctype)
  }
  await run('a', 'CRM Task', '3')
  console.log('PASS actual page.js DOM/fetch contract: Task integer name=3 and existing string IDs create/clear/refresh/select/update once without duplicate creation; invalid ID types and non-Task integer IDs stay unknown, fixed HTTP categories/no raw errors or automatic retries; simulated error-side writes never claimed absent')
  console.log('LOCAL ONLY: DOM/transport replacements, no browser, real CSRF/session, network or persistence')
})().catch(() => {
  console.error('FAIL page.js controlled contract regression')
  process.exitCode = 1
})
