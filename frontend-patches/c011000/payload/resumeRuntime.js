import { accountBoundary } from '../node_modules/frappe-ui/src/resources/accountBoundary'
import { captureResume, discardResume, pendingCreation, resumePage, resumeSectionReady, showDraftNotice } from './data/safeResume'

export function createResumeAdapter({ router, boot, stop, nextTick, read }) {
  let snapshot = null
  let supported = true
  return {
    get unsupportedEditor() { return !supported },
    stop() { if (supported) stop() },
    suspend() {
      if (accountBoundary.state !== 'ACTIVE') { stop(); return }
      try { snapshot = captureResume(router.currentRoute.value); supported = true }
      catch { supported = false }
      if (supported) stop()
    },
    discard() { discardResume(); stop() },
    async refresh(context) {
      if (!supported || !snapshot) throw Error('Current page has no safe resume adapter')
      const doctype = ['Leads', 'Lead'].includes(snapshot.name) ? 'CRM Lead' : 'CRM Deal'
      const route = router.resolve(snapshot.fullPath)
      const name = route.params.leadId || route.params.dealId
      const readable = name
        ? (await read('frappe.client.get_doc_permissions', { doctype, docname: name }))?.permissions?.read
        : (await read('frappe.client.has_permission', { doctype, docname: '', perm_type: 'read' }))?.has_permission
      context.assertCurrent()
      if (!readable) {
        discardResume()
        throw Object.assign(Error('Current read access denied'), { status: 403 })
      }
      if (pendingCreation()) {
        const create = await read('frappe.client.has_permission', { doctype: pendingCreation(), docname: '', perm_type: 'create' })
        if (!create?.has_permission) {
          discardResume()
          throw Object.assign(Error('Current create access denied'), { status: 403 })
        }
      }
      if (name) {
        await read('frappe.client.get', { doctype, name })
        await read('crm.api.activities.get_activities', { name })
      } else await read('crm.api.doc.get_data', snapshot.params)
      context.assertCurrent()
      accountBoundary.hydrate()
      await boot()
      await router.isReady()
      const deadline = Date.now() + 15000
      while (resumePage()?.epoch !== context.epoch || resumePage()?.name !== snapshot.name ||
          (name && !resumeSectionReady('activity:' + name, context.epoch))) {
        context.assertCurrent()
        if (Date.now() > deadline) throw Error('Current page did not mount')
        await new Promise(resolve => setTimeout(resolve, 25))
      }
      let revision
      do {
        revision = accountBoundary.readRevision
        await nextTick()
        await context.settleReads()
        await nextTick()
      } while (revision !== accountBoundary.readRevision)
      context.assertCurrent()
      if (router.currentRoute.value.fullPath !== snapshot.fullPath) throw Error('Route changed during recovery')
      return { commit() {}, afterCommit: showDraftNotice }
    },
  }
}
