const stages = new Set(['IDENTITY', 'IDENTITY_CONFIRMED', 'PINIA_CREATE', 'APP_CREATE',
  'FRAPPE_UI_PLUGIN', 'SPRITE_PLUGIN', 'PINIA_PLUGIN', 'ROUTER_PLUGIN',
  'TRANSLATION_PLUGIN', 'COMPONENTS', 'TELEMETRY_PLUGIN', 'DIALOG',
  'DEV_CONTEXT', 'SOCKET', 'MOUNT', 'READY'])
const failures = new Set(['NONE', 'BOUNDARY_LOCK', 'IDENTITY_UNAVAILABLE', 'IDENTITY_TIMEOUT',
  'IDENTITY_HTTP', 'IDENTITY_REDIRECT', 'IDENTITY_RESPONSE', 'IDENTITY_INVALID',
  'SESSION_CHANGED', 'PAGE_HIDDEN', 'HISTORY_RESTORED', 'ACCOUNT_CHANGED',
  'ACCESS_UNCONFIRMED', 'PLUGIN_EXCEPTION', 'ROUTER_EXCEPTION', 'CONTEXT_EXCEPTION',
  'SOCKET_EXCEPTION', 'MOUNT_EXCEPTION', 'INITIALIZATION_EXCEPTION'])

class IdentityFailure extends Error {
  constructor(code) { super('Identity check failed'); this.code = code }
}

export function createAccountBoundary(env) {
  const scope = Array.from(env.crypto.getRandomValues(new Uint32Array(4))).join('-')
  let user = null
  let state = 'BOOT_COVERED'
  let epoch = 0
  let cookieHint = env.cookie()
  let resolveReady
  let booted = false
  let flight = null
  let adapter = null
  const invalidators = new Set()
  const ready = new Promise(resolve => { resolveReady = resolve })
  let stage = 'IDENTITY'
  let failureStage = 'NONE'
  let failure = 'NONE'
  const diagnostic = () => Object.freeze({ version: 'C011100', stage, failureStage, failure })
  function publish() { env.diagnose?.(diagnostic()); env.resumeState?.(state) }
  function markStage(value) {
    if (state === 'ACTIVE' && stages.has(value)) { stage = value; publish() }
  }
  function record(code) {
    if (failure !== 'NONE') return
    failureStage = stage
    failure = failures.has(code) && code !== 'NONE' ? code : 'BOUNDARY_LOCK'
  }
  function invalidate() {
    epoch++
    let failed = false
    for (const fn of [...invalidators]) { try { fn() } catch { failed = true } }
    if (failed) throw new Error('Runtime invalidation failed')
  }
  function lock(reason = '会话或权限需要重新确认。', code = 'BOUNDARY_LOCK') {
    if (state === 'IDENTITY_REQUIRED') return
    state = 'IDENTITY_REQUIRED'
    record(code)
    env.cover(`${reason} 未保存编辑不能跨身份恢复。刷新或重新登录将放弃本标签未保存编辑。`, true)
    try { adapter?.discard?.() } catch {}
    try { invalidate() } catch {}
    publish()
    resolveReady()
  }
  function pause(code = 'PAGE_HIDDEN') {
    if (state === 'IDENTITY_REQUIRED' || state === 'SUSPENDED') return
    env.cover('标签已暂停；未保存编辑仅保留在本标签内存。返回后将重新核验身份与当前页面权限。', false)
    try { adapter?.suspend?.() } catch { return lock('无法安全暂停当前页面。') }
    state = 'SUSPENDED'
    record(code)
    try { invalidate() } catch { return lock('无法隔离旧运行域，请重新登录。') }
    publish()
  }
  const reads = new Set([
    'frappe.client.get', 'frappe.client.get_list', 'frappe.client.get_value',
    'frappe.client.get_doc_permissions', 'frappe.client.has_permission', 'frappe.client.get_single_value',
    'frappe.desk.form.load.getdoctype', 'frappe.desk.search.search_link', 'frappe.apps.get_apps',
    'crm.api.doc.get_data', 'crm.api.doc.get_assigned_users', 'crm.api.doc.get_quick_filters',
    'crm.api.doc.get_filterable_fields', 'crm.api.doc.get_group_by_fields', 'crm.api.doc.sort_options',
    'crm.api.session.get_users', 'crm.api.session.get_user_info', 'crm.api.session.get_organizations',
    'crm.api.views.get_views', 'crm.api.notifications.get_notifications',
    'crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout',
    'crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections',
    'crm.fcrm.doctype.crm_deal.api.get_deal_contacts', 'crm.api.activities.get_activities',
    'crm.domain_enrichment.api.get_enriched_fields', 'crm.integrations.api.is_call_integration_enabled',
    'crm.api.whatsapp.is_whatsapp_enabled', 'crm.api.whatsapp.is_whatsapp_installed',
    'crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.can_view_quotations',
    'crm.www.crm.get_context_for_dev', 'crm.api.get_user_signature',
    'crm.api.whatsapp.get_whatsapp_messages',
    'crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log',
    'crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_deal_quotations',
  ])
  const pending = new Set()
  let hydrationError = null
  function assertActive(expected = epoch) {
    if (env.cookie() !== cookieHint) lock('检测到账号会话变化。', 'SESSION_CHANGED')
    if (state !== 'ACTIVE' || !user || expected !== epoch || env.hidden()) {
      throw Object.assign(new Error('CRM account boundary is locked; inactive epoch'), { name: 'AbortError' })
    }
  }
  function assertRecovery(id) {
    if (env.cookie() !== cookieHint) lock('检测到账号会话变化。', 'SESSION_CHANGED')
    if (id !== epoch || env.hidden() || state === 'IDENTITY_REQUIRED') {
      throw Object.assign(new Error('Recovery superseded'), { name: 'AbortError' })
    }
  }
  function assertRequest(expected, url) {
    if (state === 'HYDRATING' && expected === epoch) {
      assertRecovery(expected)
      if (reads.has((url || '').replace(/^\/api\/method\//, ''))) return
      hydrationError ||= new Error('Current page attempted an undeclared recovery request')
      throw hydrationError
    }
    assertActive(expected)
  }
  const hydrators = new Set()
  let readRevision = 0
  function track(promise) {
    if (state !== 'HYDRATING') return
    readRevision++
    const id = epoch
    pending.add(promise)
    promise.catch(error => { if (id === epoch) hydrationError ||= error }).finally(() => pending.delete(promise))
  }
  async function settleReads() {
    const id = epoch
    while (pending.size) {
      assertRecovery(id)
      await Promise.allSettled([...pending])
    }
    assertRecovery(id)
    if (hydrationError) throw hydrationError
  }
  async function identity(id) {
    const value = await env.identify()
    assertRecovery(id)
    if (typeof value !== 'string' || !value || value === 'Guest') throw new IdentityFailure('IDENTITY_INVALID')
    if (user && user !== value) throw new IdentityFailure('ACCOUNT_CHANGED')
    return value
  }
  function resume() {
    if (env.hidden() || state === 'ACTIVE' || state === 'IDENTITY_REQUIRED') return Promise.resolve()
    if (flight?.epoch === epoch) return flight.promise
    if (booted) {
      try { adapter?.stop?.(); invalidate() }
      catch { lock('无法隔离旧运行域，请重新登录。'); return Promise.resolve() }
    }
    const id = epoch
    const promise = Promise.resolve().then(async () => {
      assertRecovery(id)
      state = 'VERIFY_IDENTITY'; publish()
      const value = await identity(id)
      let prepared
      if (booted) {
        if (!adapter) throw Error('Unsupported current page')
        state = 'HYDRATING'; hydrationError = null; pending.clear(); publish()
        let timeout
        try {
          prepared = await Promise.race([
            adapter.refresh({ epoch: id, user: value, assertCurrent: () => assertRecovery(id), settleReads }),
            new Promise((_, reject) => { timeout = setTimeout(() => reject(Error('Recovery timed out')), 15000) }),
          ])
        } finally { clearTimeout(timeout) }
        assertRecovery(id)
        state = 'VERIFY_COMMIT'; publish()
        await identity(id)
        assertRecovery(id)
        prepared.commit()
        assertRecovery(id)
      }
      user = value
      state = 'ACTIVE'
      if (!booted) { booted = true; stage = 'IDENTITY_CONFIRMED' }
      publish()
      env.uncover()
      prepared?.afterCommit?.()
      resolveReady()
    }).catch(error => {
      if (id !== epoch || state === 'IDENTITY_REQUIRED' || env.hidden()) return
      try { adapter?.stop?.() }
      catch { return lock('无法隔离旧运行域，请重新登录。') }
      if (error instanceof IdentityFailure && ['IDENTITY_INVALID', 'ACCOUNT_CHANGED', 'SESSION_CHANGED'].includes(error.code)) {
        return lock('无法确认服务端登录身份，请重新登录。', error.code)
      }
      if ([401, 403].includes(error?.status || error?.response?.status) ||
          ['PermissionError', 'AuthenticationError', 'SessionExpired'].includes(error?.exc_type)) {
        return lock('当前访问权限已撤回，请重新确认登录。', 'ACCESS_UNCONFIRMED')
      }
      try { invalidate() } catch { return lock('无法隔离恢复失败的运行域。') }
      state = 'RETRY_COVERED'
      if (!booted) record(error?.code || 'IDENTITY_UNAVAILABLE')
      publish()
      env.cover(adapter?.unsupportedEditor
        ? '当前编辑器暂不支持安全恢复。未保存内容仍在本标签，业务内容继续隐藏；可明确放弃未保存编辑并刷新，或退出登录。'
        : '无法安全恢复当前页面。旧业务内容继续隐藏，未保存编辑仍仅在本标签内存中；请联网后重试。', true, resume)
    }).finally(() => { if (flight?.epoch === id) flight = null })
    flight = { epoch: id, promise }
    return promise
  }
  function initializationFailed() {
    const code = stage === 'ROUTER_PLUGIN' ? 'ROUTER_EXCEPTION'
      : stage.endsWith('_PLUGIN') ? 'PLUGIN_EXCEPTION'
      : stage === 'DEV_CONTEXT' ? 'CONTEXT_EXCEPTION'
      : stage === 'SOCKET' ? 'SOCKET_EXCEPTION'
      : stage === 'MOUNT' ? 'MOUNT_EXCEPTION' : 'INITIALIZATION_EXCEPTION'
    lock('初始化失败，请重新确认登录。', code)
  }
  function failed(error, sensitiveRead = false) {
    if (state === 'HYDRATING') return
    const status = error?.status || error?.response?.status
    if ((sensitiveRead && error?.exc_type !== 'DoesNotExistError') || [401, 403].includes(status) ||
        ['PermissionError', 'AuthenticationError', 'SessionExpired'].includes(error?.exc_type)) {
      lock('请求失败，无法确认当前数据访问权限。', 'ACCESS_UNCONFIRMED')
    }
  }
  publish()
  env.cover('正在向服务端确认当前账号；不读取历史业务缓存。', false)
  env.on('visibilitychange', () => { if (env.hidden()) pause(); else void resume() })
  env.on('pageshow', event => { if (event.persisted) { pause('HISTORY_RESTORED'); void resume() } })
  env.on('focus', () => {
    if (env.cookie() !== cookieHint) lock('检测到账号会话变化。', 'SESSION_CHANGED')
    else if (state === 'SUSPENDED') void resume()
  })
  env.on('account-change', () => lock('另一标签的账号会话发生变化。', 'ACCOUNT_CHANGED'))
  if (!env.hidden()) void resume()
  return { scope, ready, get user() { return user }, get epoch() { return epoch }, get state() { return state },
    get diagnostic() { return diagnostic() }, assertActive, failed, lock, markStage, initializationFailed,
    resume, pause, assertRequest, track, get readRevision() { return readRevision },
    onHydrate(fn) { hydrators.add(fn); return () => hydrators.delete(fn) },
    hydrate() { for (const fn of [...hydrators]) fn() },
    setAdapter(value) { adapter = value },
    onInvalidate(fn) { invalidators.add(fn); return () => invalidators.delete(fn) },
    changed() { try { env.broadcast() } finally { lock('账号会话发生变化。', 'ACCOUNT_CHANGED') } } }
}

function browserEnvironment() {
  const overlayId = 'crm-account-boundary'
  let channel
  let diagnosticText = ''
  function diagnose(value) {
    document.documentElement.setAttribute('data-crm-diagnostic-version', value.version)
    document.documentElement.setAttribute('data-crm-init-stage', value.stage)
    document.documentElement.setAttribute('data-crm-first-failure-stage', value.failureStage)
    document.documentElement.setAttribute('data-crm-first-failure', value.failure)
    diagnosticText = `本地诊断 ${value.version} / ${value.stage} / ${value.failureStage} / ${value.failure}`
    const node = document.getElementById('crm-initialization-diagnostic')
    if (node) node.textContent = diagnosticText
  }
  try { channel = new BroadcastChannel('crm-account-boundary-c011000') } catch {}
  const style = document.createElement('style')
  style.textContent = 'html[data-crm-account-blocked] body > :not(#crm-account-boundary),html[data-crm-account-blocked] body > :not(#crm-account-boundary) *{visibility:hidden!important;pointer-events:none!important}#crm-account-boundary{position:fixed;inset:0;z-index:2147483647;background:#fff;color:#111;padding:2rem;overflow:auto;font:16px/1.6 sans-serif}#crm-account-boundary button,#crm-account-boundary a{display:inline-block;margin:1rem;padding:.5rem;border:1px solid #888}'
  document.head.append(style)
  function cover(message, actionable, retry) {
    document.documentElement.setAttribute('data-crm-account-blocked', '')
    const render = () => {
      let overlay = document.getElementById(overlayId)
      if (!overlay) {
        overlay = document.createElement('section')
        overlay.id = overlayId
        overlay.setAttribute('role', 'alertdialog')
        overlay.setAttribute('aria-modal', 'true')
        overlay.setAttribute('aria-label', 'CRM账号安全边界')
        document.body.append(overlay)
      }
      overlay.replaceChildren()
      const text = document.createElement('p')
      text.textContent = message
      const diagnostic = document.createElement('p')
      diagnostic.id = 'crm-initialization-diagnostic'
      diagnostic.textContent = diagnosticText
      overlay.append(text, diagnostic)
      if (actionable) {
        if (retry) {
          const button = document.createElement('button')
          button.textContent = '重试安全恢复'
          button.onclick = () => { button.disabled = true; void retry() }
          overlay.append(button)
        }
        const reload = document.createElement('button')
        reload.textContent = '放弃未保存编辑并刷新'
        reload.onclick = () => location.reload()
        const login = document.createElement('a')
        login.textContent = '放弃未保存编辑，前往标准登录'
        login.href = '/login?redirect-to=/crm'
        const logout = document.createElement('button')
        logout.textContent = '退出当前登录（放弃未保存编辑）'
        logout.onclick = async () => {
          logout.disabled = true
          try {
            const response = await fetch('/api/method/logout', {
              method: 'POST', credentials: 'same-origin', cache: 'no-store',
              headers: { Accept: 'application/json', 'X-Frappe-CSRF-Token': window.csrf_token || '' },
            })
            if (!response.ok) throw new Error('Logout failed')
            try { channel?.postMessage('changed') } catch {}
            location.assign('/login?redirect-to=/crm')
          } catch {
            text.textContent = '退出登录未成功，请检查网络后重试；旧业务内容继续隐藏。未保存编辑仍在本标签内存中。'
            logout.disabled = false
          }
        }
        overlay.append(reload, login, logout)
      }
    }
    if (document.body) render()
    else document.addEventListener('DOMContentLoaded', render, { once: true })
  }
  return {
    crypto: window.crypto, cookie: () => document.cookie, hidden: () => document.visibilityState === 'hidden',
    cover, diagnose,
    resumeState(value) { document.documentElement.setAttribute('data-crm-resume-state', value) },
    uncover() {
      document.documentElement.removeAttribute('data-crm-account-blocked')
      document.getElementById(overlayId)?.remove()
    },
    on(type, fn) {
      if (type === 'account-change') { if (channel) channel.onmessage = fn }
      else (type === 'visibilitychange' ? document : window).addEventListener(type, fn)
    },
    broadcast() { try { channel?.postMessage('changed') } catch {} },
    async identify() {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 15000)
      try {
        const response = await fetch('/api/method/frappe.auth.get_logged_user', {
          method: 'GET', credentials: 'same-origin', cache: 'no-store',
          headers: { Accept: 'application/json' }, signal: controller.signal,
        })
        if (response.redirected) throw new IdentityFailure('IDENTITY_REDIRECT')
        if (!response.ok) throw new IdentityFailure('IDENTITY_HTTP')
        let value
        try { value = await response.json() }
        catch { throw new IdentityFailure('IDENTITY_RESPONSE') }
        return value?.message
      } catch (error) {
        if (controller.signal.aborted) throw new IdentityFailure('IDENTITY_TIMEOUT')
        throw error
      } finally { clearTimeout(timeout) }
    },
  }
}

export const accountBoundary = createAccountBoundary(browserEnvironment())
