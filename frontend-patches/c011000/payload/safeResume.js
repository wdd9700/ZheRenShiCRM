import { accountBoundary } from '../../node_modules/frappe-ui/src/resources/accountBoundary'

const documents = new Map()
let drafts = new Map()
let page = null
let pendingCreate = null
let notice = null
const clone = value => JSON.parse(JSON.stringify(value ?? null))
const equal = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)
const key = (doctype, name) => JSON.stringify([doctype, name || ''])
const supported = new Set(['CRM Lead', 'CRM Deal'])
const scalarTypes = new Set(['Data', 'Small Text', 'Text', 'Long Text', 'Text Editor', 'Code',
  'Select', 'Link', 'Dynamic Link', 'Check', 'Int', 'Float', 'Currency', 'Percent', 'Date', 'Datetime',
  'Time', 'Phone', 'Autocomplete', 'Rating', 'Duration'])

export function registerResumeDocument(doctype, name, document, getFields, getPermissions) {
  if (!supported.has(doctype)) return () => {}
  const id = key(doctype, name)
  const entry = { doctype, name, document, getFields, getPermissions, epoch: accountBoundary.epoch,
    base: name ? null : clone(document.doc) }
  documents.set(id, entry)
  function retire() {
    if (entry.epoch === accountBoundary.epoch) return
    entry.document.doc = null
    entry.document.originalDoc = null
    entry.base = null
    if (documents.get(id) === entry) documents.delete(id)
    stopInvalidate(); stopHydrate()
  }
  const stopInvalidate = accountBoundary.onInvalidate(() => {
    if (accountBoundary.state === 'IDENTITY_REQUIRED') retire()
  })
  const stopHydrate = accountBoundary.onHydrate(retire)
  return () => { if (documents.get(id) === entry) documents.delete(id) }
}

export function setCreationBaseline(doctype, document) {
  const entry = documents.get(key(doctype, ''))
  if (entry?.document === document) entry.base = clone(document.doc)
}

export function registerResumePage(name, getParams) {
  const entry = { name, getParams, epoch: accountBoundary.epoch }
  page = entry
  return () => { if (page === entry) page = null }
}

const unsavedEditors = new Set()
export function registerUnsavedEditor(hasUnsaved, clear) {
  const entry = { epoch: accountBoundary.epoch, hasUnsaved, clear }
  unsavedEditors.add(entry)
  const stop = accountBoundary.onInvalidate(() => {
    if (accountBoundary.state === 'IDENTITY_REQUIRED') { clear(); unsavedEditors.delete(entry); stop() }
  })
  return () => { unsavedEditors.delete(entry); stop() }
}

const sections = new Map()
export function registerResumeSection(name) {
  const epoch = accountBoundary.epoch
  sections.set(name, epoch)
  return () => { if (sections.get(name) === epoch) sections.delete(name) }
}
export function resumeSectionReady(name, epoch) { return sections.get(name) === epoch }

export function reopenCreation(doctype) { return pendingCreate === doctype }
let listParams = null
export function resumeListParams(doctype, fallback) {
  return accountBoundary.state === 'HYDRATING' && listParams?.doctype === doctype ? clone(listParams) : fallback
}

export function captureResume(route) {
  notice?.remove(); notice = null
  const allowed = ['Leads', 'Deals', 'Lead', 'Deal'].includes(route.name)
  const creating = [...documents.values()].some(entry => !entry.name && entry.epoch === accountBoundary.epoch)
  const editors = globalThis.document?.querySelectorAll?.('[contenteditable="true"]:not([data-crm-field])') || []
  const hasEditorDraft = [...unsavedEditors].some(entry => entry.hasUnsaved())
  if (!allowed || page?.name !== route.name || hasEditorDraft || [...editors].some(editor => editor.textContent?.trim()) ||
      (globalThis.document?.querySelector?.('[role="dialog"]') && !creating)) {
    throw Error('当前编辑器暂不支持安全恢复；未保存内容仍在本标签。可放弃未保存编辑并刷新，或退出登录。')
  }
  const captured = new Map(drafts)
  pendingCreate = null
  for (const [id, entry] of documents) {
    if (entry.epoch !== accountBoundary.epoch) continue
    if (!entry.name) pendingCreate = entry.doctype
    const original = entry.name ? entry.document.originalDoc : entry.base
    const current = entry.document.doc
    if (!original || !current) continue
    const changes = {}
    const fields = entry.getFields() || []
    for (const name of new Set([...Object.keys(current), ...Object.keys(original)])) {
      if (equal(current[name], original[name])) continue
      const field = fields.find(field => field.fieldname === name)
      if (!field || !scalarTypes.has(field.fieldtype) || field.hidden || field.read_only || Number(field.permlevel)) {
        throw Error('Unsaved field has no safe draft adapter')
      }
      changes[name] = { base: clone(original[name]), value: clone(current[name]) }
    }
    if (Object.keys(changes).length) captured.set(id, { user: accountBoundary.user,
      changes: { ...captured.get(id)?.changes, ...changes } })
  }
  drafts = captured
  listParams = clone(page.getParams?.())
  return { name: route.name, fullPath: route.fullPath, params: clone(listParams) }
}

export function discardResume() {
  drafts.clear(); pendingCreate = null; listParams = null
  for (const entry of unsavedEditors) entry.clear()
  notice?.remove(); notice = null
}

export function resumePage() { return page }
export function pendingCreation() { return pendingCreate }

export function planDrafts(user) {
  const plans = []
  for (const [id, draft] of drafts) {
    const entry = documents.get(id)
    if (draft.user !== user) { drafts.delete(id); continue }
    if (!entry || entry.epoch !== accountBoundary.epoch) continue
    const permission = entry.getPermissions()?.permissions
    if (entry.name ? (!permission?.read || !permission.write) : !permission?.create) {
      drafts.delete(id); continue
    }
    const visible = new Map((entry.getFields() || []).filter(field => !field.hidden && !field.read_only &&
      !Number(field.permlevel) && scalarTypes.has(field.fieldtype)).map(field => [field.fieldname, field]))
    for (const field of Object.keys(draft.changes)) if (!visible.has(field)) delete draft.changes[field]
    const values = {}
    let conflict = false
    for (const [field, change] of Object.entries(draft.changes)) {
      if (!visible.has(field)) continue
      const fresh = entry.document.doc?.[field]
      if (!equal(fresh, change.base) && !equal(fresh, change.value)) { conflict = true; continue }
      values[field] = clone(change.value)
    }
    if (Object.keys(values).length || conflict) plans.push({ id, entry, values, conflict })
  }
  return plans
}

export function restoreDraft(plan) {
  accountBoundary.assertActive(plan.entry.epoch)
  if (documents.get(plan.id) !== plan.entry) throw Error('Draft target changed')
  const current = planDrafts(accountBoundary.user).find(item => item.id === plan.id)
  if (!current || current.conflict) return false
  Object.assign(current.entry.document.doc, clone(current.values))
  drafts.delete(current.id)
  return true
}

export function showDraftNotice() {
  notice?.remove(); notice = null
  const plans = planDrafts(accountBoundary.user)
  if (!plans.length) return
  notice = document.createElement('aside')
  notice.setAttribute('role', 'status')
  notice.style.cssText = 'position:fixed;bottom:1rem;left:1rem;right:1rem;z-index:2147483000;background:white;color:black;border:1px solid #888;padding:1rem'
  const text = document.createElement('p')
  text.textContent = plans.some(plan => plan.conflict)
    ? '服务端数据已变化，未提交编辑存在冲突；未自动覆盖。请保留本标签并人工核对，或明确放弃草稿。'
    : '同身份与当前字段权限已重新核验。有本标签的未提交编辑，可明确恢复；不会自动保存。'
  notice.append(text)
  if (!plans.some(plan => plan.conflict)) {
    const restore = document.createElement('button')
    restore.textContent = '恢复未提交编辑（不保存）'
    restore.onclick = () => { for (const plan of plans) restoreDraft(plan); notice?.remove(); notice = null }
    notice.append(restore)
  }
  const discard = document.createElement('button')
  discard.textContent = '放弃本标签草稿'
  discard.onclick = discardResume
  notice.append(discard)
  document.body.append(notice)
}
