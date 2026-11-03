(() => {
  const root = document.getElementById('team-activities')
  if (!root) return
  const el = (id) => document.getElementById(`activity-${id}`)
  const status = (message) => { el('status').textContent = message }
  let current = null
  function saveError(category, code) {
    const http = Number.isInteger(code) && code >= 100 && code <= 599 ? `（HTTP ${code}）` : ''
    return new Error(`${category}${http}。保存结果未确认；请先只读回查活动列表或记录，勿盲目重复提交。`)
  }
  async function call(method, data) {
    let response
    try {
      response = await fetch(`/api/method/team_access.api.${method}`, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': root.dataset.csrf },
        body: JSON.stringify(data),
      })
    } catch {
      throw saveError('网络或连接异常')
    }
    let body
    try {
      body = await response.json()
    } catch {
      throw saveError('响应格式或传输异常', response.status)
    }
    if (!response.ok) {
      const category = { 400: '请求格式错误', 401: '身份认证失败', 403: '访问或会话校验被拒绝', 417: '输入或业务校验失败' }[response.status]
      throw saveError(category || (response.status >= 500 ? '服务器处理异常' : 'HTTP 请求失败'), response.status)
    }
    if (!body || typeof body !== 'object' || Array.isArray(body) || body.exc) throw saveError('服务端响应异常', response.status)
    const saved = body.message
    if (!saved || typeof saved !== 'object' || Array.isArray(saved) || typeof saved.name !== 'string' || !saved.name || saved.doctype !== data.document.doctype) throw saveError('保存确认响应不完整', response.status)
    return saved
  }
  async function get(method, data) {
    const query = new URLSearchParams(data)
    const response = await fetch(`/api/method/team_access.api.${method}?${query}`, { credentials: 'same-origin', cache: 'no-store' })
    const body = await response.json()
    if (body.team_access_limit) throw new Error('记录超过安全扫描上限（2000）；本请求已被拒绝，并非空列表。请联系管理员评估扩容权限方案。')
    if (!response.ok || body.exc) throw new Error('请求被拒绝或失败')
    return body.message
  }
  function edit(record = null) {
    current = record
    el('name').value = record?.name || ''
    el('title').value = record?.title || ''
    el('content').value = record?.content || record?.description || ''
    el('parent-type').value = record?.reference_doctype || ''
    el('parent').value = record?.reference_docname || ''
    el('visibility').value = record?.custom_team_visibility || 'Private'
    el('collaborator').value = record?.custom_team_collaborator || ''
    el('assignee').value = record?.assigned_to || ''
    const owner = !record || record.owner === root.dataset.user || root.dataset.user === 'Administrator'
    el('acl').disabled = !owner
    const writer = owner || record?.custom_team_collaborator === root.dataset.user || record?.assigned_to === root.dataset.user
    el('title').readOnly = !writer
    el('content').readOnly = !writer
    el('form').querySelector('button[type=submit]').disabled = !writer
    el('assignee-label').hidden = el('type').value !== 'CRM Task'
    el('access').textContent = writer ? '你可以编辑正文；共享不会使其他父记录读者获得编辑权。' : '你仅有阅读权限。'
  }
  async function refresh() {
    try {
      const rows = await get('list_activities', { doctype: el('type').value })
      el('list').replaceChildren()
      for (const row of rows) {
        const li = document.createElement('li')
        const button = document.createElement('button')
        button.type = 'button'
        button.textContent = `${row.title} — ${row.custom_team_visibility || 'Private'} — ${row.owner}`
        button.onclick = () => edit(row)
        li.append(button)
        el('list').append(li)
      }
      status(`可读活动：${rows.length}；每次刷新重新校验权限。`)
    } catch (error) { status(error.message) }
  }
  el('new').onclick = () => edit()
  el('refresh').onclick = refresh
  el('type').onchange = () => { edit(); refresh() }
  async function parents() {
    el('parents').replaceChildren()
    if (!el('parent-type').value) return
    try {
      const rows = await get('parent_options', { doctype: el('parent-type').value, txt: el('parent').value })
      for (const row of rows) {
        const option = document.createElement('option')
        option.value = row.name
        el('parents').append(option)
      }
    } catch (error) { status(error.message) }
  }
  el('parent-type').onchange = () => { el('parent').value = ''; parents() }
  el('parent').oninput = parents
  el('form').onsubmit = async (event) => {
    event.preventDefault()
    const document = { doctype: el('type').value, title: el('title').value }
    if (current) document.name = current.name
    document[document.doctype === 'FCRM Note' ? 'content' : 'description'] = el('content').value
    if (!el('acl').disabled) {
      Object.assign(document, {
        reference_doctype: el('parent-type').value, reference_docname: el('parent').value,
        custom_team_visibility: el('visibility').value, custom_team_collaborator: el('collaborator').value,
      })
      if (document.doctype === 'CRM Task') document.assigned_to = el('assignee').value
    }
    if (document.custom_team_visibility === 'Shared' && !window.confirm('确认发布当前正文给父记录的所有现有和未来读者？不授予编辑权，也不公开既往私密版本或附件。含私有附件的记录不能发布。')) return
    if ((document.custom_team_collaborator && document.custom_team_collaborator !== current?.custom_team_collaborator) || (document.assigned_to && document.assigned_to !== current?.assigned_to)) {
      if (!window.confirm('确认授权此人读写Private正文及既往历史？关联父记录必须保持可读；对方不能再授权他人。')) return
    }
    try {
      const saved = await call('save_activity', { document }, true)
      edit(saved)
      await refresh()
      status('保存成功；授权变更只影响后续服务器请求，已读副本无法撤回。')
    } catch (error) { status(error.message) }
  }
  edit()
  refresh()
})()
