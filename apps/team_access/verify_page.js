const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.join(__dirname, 'team_access/public/page.js'), 'utf8')
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

async function run(user, doctype) {
  const elements = new Map()
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, { value: '', disabled: false, hidden: false, textContent: '', replaceChildren() {}, append() {}, querySelector: () => element('submit') })
    return elements.get(id)
  }
  element('team-activities').dataset = { user, csrf: secret }
  element('activity-type').value = doctype
  const calls = []
  const writes = []
  let scenario = { code: 200 }
  const fetch = async (url, options = {}) => {
    if (options.method !== 'POST') return { ok: true, json: async () => ({ message: [] }) }
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
        if (scenario.code >= 400 || scenario.exc) return { exc: secret, exc_type: secret, message: secret, _server_messages: secret, traceback: secret, token: secret }
        return { message: { ...document, name: 'synthetic-result', owner: user } }
      },
    }
  }
  vm.runInNewContext(source, { document: { getElementById: element, createElement: () => element(Symbol()) }, fetch, URLSearchParams, window: { confirm: () => true } })
  await new Promise((resolve) => setImmediate(resolve))
  const submit = async () => {
    element('activity-new').onclick()
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
    assert.equal(payload.document.doctype, doctype)
    assert.equal(payload.document.custom_team_visibility, 'Private')
    assert.equal(payload.document.custom_team_collaborator, '')
    assert.equal(payload.document.reference_doctype, user === 'a' ? '' : 'CRM Lead')
    assert.equal(payload.document[doctype === 'FCRM Note' ? 'content' : 'description'], `合成 <b>content</b>, comma ${secret}`)
    return element('activity-status').textContent
  }
  assert.match(await submit(), /保存成功/)
  for (scenario of cases) {
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
  console.log('PASS actual page.js DOM/fetch contract: Note/Task success, fixed HTTP categories, non-JSON/network/response-loss unknown results, no raw errors/secrets or automatic retries; simulated error-side writes never claimed absent')
  console.log('LOCAL ONLY: DOM/transport replacements, no browser, real CSRF/session, network or persistence')
})().catch(() => {
  console.error('FAIL page.js controlled contract regression')
  process.exitCode = 1
})
