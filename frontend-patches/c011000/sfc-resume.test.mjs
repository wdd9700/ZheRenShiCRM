import { afterEach, expect, test, vi } from 'vitest'
import { nextTick } from 'vue'

vi.mock('socket.io-client', () => ({
  io() {
    const listeners = new Map()
    const socket = {
      on(event, fn) { listeners.set(event, fn); return socket },
      off(event) { listeners.delete(event); return socket },
      emit() { return socket },
      removeAllListeners() { listeners.clear(); return socket },
      disconnect() { return socket },
      connected: false,
      io: { on() {}, off() {} },
    }
    return socket
  },
}))

const identity = 'synthetic-sfc@example.invalid'
const draft = 'SYNTHETIC-DA2177-SFC-DRAFT'
const user = { name: identity, email: identity, full_name: 'Synthetic SFC Sales',
  first_name: 'Synthetic', last_name: 'Sales', role: 'Sales User', user_type: 'System User' }
const leadFields = [
  { fieldname: 'first_name', label: 'First Name', fieldtype: 'Data', reqd: 1, permlevel: 0 },
  { fieldname: 'status', label: 'Status', fieldtype: 'Select', options: 'New', permlevel: 0 },
  { fieldname: 'lead_owner', label: 'Lead Owner', fieldtype: 'Link', options: 'User', permlevel: 0 },
  { fieldname: 'no_of_employees', label: 'No of Employees', fieldtype: 'Select', options: '1-10', permlevel: 0 },
]
const metaFields = {
  'CRM Lead': leadFields,
  'FCRM Settings': [],
  'CRM Lead Status': [],
  'CRM Deal Status': [],
  'CRM Communication Status': [],
  'CRM Availability Status': [],
  'CRM Form Script': [],
  'CRM Organization': [],
  User: [],
}
const listRows = {
  'CRM Lead Status': [{ name: 'New', color: 'gray', position: 1, type: 'Open' }],
  'CRM Deal Status': [{ name: 'New', color: 'gray', position: 1, type: 'Open' }],
  'CRM Communication Status': [],
  'CRM Availability Status': [{ name: 'Active', category: 'Active', color: 'green', enabled: 1, position: 1 }],
  'CRM Form Script': [],
}
function response(message) {
  return new Response(JSON.stringify({ message }), { status: 200, headers: { 'Content-Type': 'application/json' } })
}
function bodyFor(method, params) {
  switch (method) {
    case 'frappe.auth.get_logged_user': return response(identity)
    case 'crm.www.crm.get_context_for_dev': return response({
      frappe_version: '15.125.0', has_automation_engine: false, default_route: '/crm',
      site_name: 'synthetic.invalid', socketio_port: 9000, read_only_mode: false,
      csrf_token: 'synthetic-not-a-credential', setup_complete: 1,
      sysdefaults: { currency: 'USD', date_format: 'yyyy-mm-dd', time_format: 'HH:mm:ss',
        float_precision: 3, currency_precision: 2, number_format: '#,###.##' },
      is_demo_site: false, demo_data_created: false, is_fc_site: false,
      translated_doctypes: [], translated_messages: {}, timezone: { system: 'UTC', user: 'UTC' },
      state_options: {},
    })
    case 'frappe.utils.telemetry.pulse.client.boot_config':
      return response({ enabled: false, site: 'synthetic.invalid', user: identity })
    case 'frappe.onboarding.get_onboarding_status':
      return response({ frappecrm_onboarding_status: [
        { name: 'create_first_lead', completed: true },
        { name: 'connect_your_email', completed: true },
        { name: 'invite_your_team', completed: true },
        { name: 'convert_lead_to_deal', completed: true },
        { name: 'create_first_task', completed: true },
      ] })
    case 'crm.api.session.get_users': return response([[user], [user]])
    case 'crm.api.session.get_user_info': return response([user])
    case 'crm.api.session.get_organizations':
    case 'crm.api.views.get_views':
    case 'crm.api.notifications.get_notifications':
    case 'frappe.apps.get_apps':
    case 'crm.api.doc.get_quick_filters': return response([])
    case 'crm.api.doc.get_filterable_fields': return response(leadFields)
    case 'crm.api.doc.sort_options': return response([{ fieldname: 'modified', label: 'Last Modified' }])
    case 'frappe.client.has_permission': {
      if (params.doctype !== 'CRM Lead' || !['read', 'create'].includes(params.perm_type)) break
      return response({ has_permission: true })
    }
    case 'frappe.client.get_list': {
      if (!Object.hasOwn(listRows, params.doctype)) break
      return response(listRows[params.doctype])
    }
    case 'frappe.desk.form.load.getdoctype': {
      if (!Object.hasOwn(metaFields, params.doctype)) break
      return new Response(JSON.stringify({ docs: [{ doctype: 'DocType', name: params.doctype,
        fields: metaFields[params.doctype], permissions: [{ role: 'Sales User', read: 1, write: 1, create: 1 }] }],
      user_settings: '{}' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    case 'frappe.client.get': {
      if (params.doctype !== 'FCRM Settings' || params.name !== 'FCRM Settings') break
      return response({ doctype: 'FCRM Settings', name: 'FCRM Settings', brand_name: 'Synthetic CRM',
        dropdown_items: [], setup_completed: 1 })
    }
    case 'crm.api.doc.get_data': {
      if (params.doctype !== 'CRM Lead') break
      return response({ data: [], columns: [{ key: 'first_name', label: 'First Name', width: '10rem' }],
        rows: ['name', 'first_name'], fields: ['name', 'first_name'], view_type: 'list', views: [],
        row_count: 0, total_count: 0, page_length: 20, page_length_count: 20 })
    }
    case 'crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout': {
      if (params.doctype !== 'CRM Lead' || params.type !== 'Quick Entry') break
      return response([{ name: 'synthetic_main', label: '', sections: [{ name: 'synthetic_details',
        label: '', columns: [{ name: 'synthetic_column', fields: leadFields }] }] }])
    }
    case 'crm.integrations.api.is_call_integration_enabled':
      return response({ integrations: {}, default_calling_medium: '' })
    case 'crm.api.whatsapp.is_whatsapp_enabled':
    case 'crm.api.whatsapp.is_whatsapp_installed':
    case 'crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.can_view_quotations': return response(false)
  }
  throw Error('SFC_FIXTURE_UNDECLARED_REQUEST:' + method)
}
function errorEvidence(error) {
  const text = String(error?.message || '')
  const kind = text.includes('Resource request superseded') ? 'RESOURCE_SUPERSEDED'
    : text.includes('undeclared recovery request') ? 'RECOVERY_UNDECLARED'
    : text.startsWith('SFC_FIXTURE_UNDECLARED_REQUEST:') ? text
    : ['TypeError', 'SyntaxError', 'AbortError'].includes(error?.name) ? error.name : 'OTHER_REJECTION'
  const locations = String(error?.stack || '').split('\n').filter(line => /(?:src|node_modules)\/.*:\d+:\d+/.test(line)).slice(0, 4)
  return { kind, locations }
}

let boundary, hidden = false
const requests = [], rejected = [], unknown = []
let tracking
function diagnostics() {
  return JSON.stringify({ boundary: boundary?.diagnostic, state: boundary?.state,
    rejected: rejected.slice(0, 8), unknown, requests: requests.map(({ method, epoch }) => ({ method, epoch })) })
}
async function until(check, label, milliseconds = 8000) {
  const deadline = Date.now() + milliseconds
  while (!check()) {
    if (Date.now() > deadline) throw Error('SFC_WAIT_FAILED:' + label + '\n' + diagnostics())
    await new Promise(resolve => setTimeout(resolve, 10))
    await nextTick()
  }
}
function button(label) {
  return [...document.querySelectorAll('button')].find(node => node.textContent.trim() === label)
}
function firstName() {
  return document.querySelector('input[placeholder="Enter First Name"], input[aria-label="First Name"], [data-fieldname="first_name"] input')
}
function visibility(value) {
  hidden = value
  document.dispatchEvent(new Event('visibilitychange'))
}

afterEach(() => {
  boundary?.lock('Synthetic test cleanup')
  tracking?.mockRestore()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  document.body.replaceChildren()
  document.cookie = 'user_id=; Max-Age=0; Path=/'
})

test('real App/Leads/FieldLayout and transport preserve a creation draft across a fresh runtime', async () => {
  document.body.innerHTML = '<div id="app"></div>'
  window.history.replaceState({}, '', '/crm/leads/view/list')
  localStorage.clear()
  localStorage.setItem('crm_setup_completed', '1')
  document.cookie = `user_id=${encodeURIComponent(identity)}; Path=/`
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1280 })
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => hidden ? 'hidden' : 'visible' })
  window.site_name = 'synthetic.invalid'
  window.csrf_token = 'synthetic-not-a-credential'
  window.timezone = { system: 'UTC', user: 'UTC' }
  window.translated_messages = {}
  vi.stubGlobal('fetch', async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href)
    const method = url.pathname.replace(/^\/api\/method\//, '')
    const params = Object.fromEntries(url.searchParams)
    if (options.body) Object.assign(params, JSON.parse(options.body))
    requests.push({ method, epoch: boundary?.epoch })
    if (!url.pathname.startsWith('/api/method/')) {
      unknown.push(method); throw Error('SFC_FIXTURE_UNDECLARED_REQUEST:' + method)
    }
    await new Promise((resolve, reject) => {
      if (options.signal?.aborted) return reject(new DOMException('Synthetic aborted transport', 'AbortError'))
      const aborted = () => { clearTimeout(timer); reject(new DOMException('Synthetic aborted transport', 'AbortError')) }
      const timer = setTimeout(() => { options.signal?.removeEventListener('abort', aborted); resolve() }, 1)
      options.signal?.addEventListener('abort', aborted, { once: true })
    })
    try { return bodyFor(method, params) }
    catch (error) { unknown.push(method); throw error }
  })
  ;({ accountBoundary: boundary } = await import('../../node_modules/frappe-ui/src/resources/accountBoundary'))
  const originalTrack = boundary.track.bind(boundary)
  tracking = vi.spyOn(boundary, 'track').mockImplementation(promise => {
    const epoch = boundary.epoch
    const state = boundary.state
    promise.catch(error => rejected.push({ epoch, state, ...errorEvidence(error) }))
    return originalTrack(promise)
  })
  await import('@/main')
  await boundary.ready
  await until(() => button('Create') && document.body.textContent.includes('No leads yet'), 'initial actual Leads mount')
  expect(unknown, diagnostics()).toEqual([])
  button('Create').click()
  await until(() => firstName(), 'actual LeadModal field control')
  const input = firstName()
  input.value = draft
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
  await nextTick()
  const safe = await import('@/data/safeResume')
  visibility(true)
  expect(boundary.state, diagnostics()).toBe('SUSPENDED')
  expect(document.documentElement.hasAttribute('data-crm-account-blocked')).toBe(true)
  visibility(false)
  await boundary.resume()
  const firstAttempt = boundary.state
  if (firstAttempt !== 'ACTIVE') await boundary.resume()
  expect(firstAttempt, diagnostics()).toBe('ACTIVE')
  expect(boundary.state, diagnostics()).toBe('ACTIVE')
  expect(unknown, diagnostics()).toEqual([])
  expect(safe.planDrafts(identity).some(plan => plan.values.first_name === draft), diagnostics()).toBe(true)
  expect(firstName()?.value).not.toBe(draft)
  const restore = button('恢复未提交编辑（不保存）')
  expect(restore, diagnostics()).toBeTruthy()
  restore.click()
  await nextTick()
  expect(firstName()?.value, diagnostics()).toBe(draft)
  expect(requests.some(({ method }) => [
    'frappe.client.insert', 'frappe.client.set_value',
    'frappe.onboarding.update_user_onboarding_status',
  ].includes(method)), diagnostics()).toBe(false)
}, 30000)
