export function createAccountBoundary(env) {
  const scope = Array.from(env.crypto.getRandomValues(new Uint32Array(4))).join('-')
  let user = null
  let locked = false
  let cookieHint = env.cookie()
  let resolveReady
  const ready = new Promise((resolve) => { resolveReady = resolve })

  function lock(reason = '会话或权限需要重新确认。') {
    locked = true
    env.cover(`${reason} 未保存编辑仍仅在本标签内存中，不能跨身份恢复。刷新或重新登录将放弃本标签未保存编辑。`, true)
  }

  function assertActive() {
    if (env.cookie() !== cookieHint) lock('检测到账号会话变化。')
    if (locked || !user) throw new Error('CRM account boundary is locked; reload required')
  }

  function failed(error, sensitiveRead = false) {
    const status = error?.status || error?.response?.status
    if ((sensitiveRead && error?.exc_type !== 'DoesNotExistError') || [401, 403].includes(status) ||
        ['PermissionError', 'AuthenticationError', 'SessionExpired'].includes(error?.exc_type)) {
      lock('请求失败，无法确认当前数据访问权限。')
    }
  }

  env.cover('正在向服务端确认当前账号；不读取历史业务缓存。', false)
  env.on('visibilitychange', () => {
    if (env.hidden()) lock('标签曾进入后台，请刷新重新确认账号与业务权限。')
  })
  env.on('pageshow', (event) => { if (event.persisted) lock('页面从浏览器历史恢复。') })
  env.on('focus', () => {
    if (env.cookie() !== cookieHint) lock('检测到账号会话变化。')
  })
  env.on('account-change', () => lock('另一标签的账号会话发生变化。'))

  Promise.resolve().then(() => env.identify()).then((identity) => {
    if (typeof identity !== 'string' || !identity || identity === 'Guest') {
      throw new Error('Authenticated server identity required')
    }
    if (env.cookie() !== cookieHint) throw new Error('Session changed during identity check')
    if (locked || env.hidden()) throw new Error('Page is not active')
    user = identity
    env.uncover()
    resolveReady()
  }).catch(() => {
    lock('无法确认服务端登录身份，请联网后刷新或重新登录。')
    resolveReady()
  })

  return { scope, ready, get user() { return user }, assertActive, failed, lock,
    changed() { env.broadcast(); lock('账号会话发生变化。') } }
}

function browserEnvironment() {
  const overlayId = 'crm-account-boundary'
  let channel
  try { channel = new BroadcastChannel('crm-account-boundary-c011000') } catch {}
  const style = document.createElement('style')
  style.textContent = 'html[data-crm-account-blocked] body > :not(#crm-account-boundary),html[data-crm-account-blocked] body > :not(#crm-account-boundary) *{visibility:hidden!important;pointer-events:none!important}#crm-account-boundary{position:fixed;inset:0;z-index:2147483647;background:#fff;color:#111;padding:2rem;overflow:auto;font:16px/1.6 sans-serif}#crm-account-boundary button,#crm-account-boundary a{display:inline-block;margin:1rem;padding:.5rem;border:1px solid #888}'
  document.head.append(style)
  function cover(message, actionable) {
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
      overlay.append(text)
      if (actionable) {
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
            channel?.postMessage('changed')
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
    crypto: window.crypto,
    cookie: () => document.cookie,
    hidden: () => document.visibilityState === 'hidden',
    cover,
    uncover() {
      document.documentElement.removeAttribute('data-crm-account-blocked')
      document.getElementById(overlayId)?.remove()
    },
    on(type, fn) {
      if (type === 'account-change') { if (channel) channel.onmessage = fn }
      else (type === 'visibilitychange' ? document : window).addEventListener(type, fn)
    },
    broadcast() { channel?.postMessage('changed') },
    async identify() {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 15000)
      try {
        const response = await fetch('/api/method/frappe.auth.get_logged_user', {
          method: 'GET', credentials: 'same-origin', cache: 'no-store',
          headers: { Accept: 'application/json' }, signal: controller.signal,
        })
        if (!response.ok || response.redirected) throw new Error('Identity unavailable')
        return (await response.json()).message
      } finally { clearTimeout(timeout) }
    },
  }
}

export const accountBoundary = createAccountBoundary(browserEnvironment())
