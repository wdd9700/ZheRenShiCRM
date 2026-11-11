const endpoints = new Set([
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
  'crm.www.crm.get_context_for_dev', 'crm.api.get_user_signature', 'crm.api.get_unsubscribed_emails',
  'crm.api.whatsapp.get_whatsapp_messages', 'crm.fcrm.doctype.crm_call_log.crm_call_log.get_call_log',
  'crm.fcrm.doctype.erpnext_crm_settings.erpnext_crm_settings.get_deal_quotations',
  'frappe.onboarding.get_onboarding_status', 'frappe.onboarding.update_user_onboarding_status',
  'frappe.utils.telemetry.pulse.client.boot_config', 'frappe.auth.get_logged_user',
  'frappe.client.insert', 'frappe.client.set_value', 'frappe.client.delete', 'login', 'logout',
])
const states = new Set(['BOOT_COVERED', 'BOOT_WAIT_VISIBLE', 'ACTIVE', 'HYDRATING',
  'VERIFY_IDENTITY', 'VERIFY_COMMIT', 'SUSPENDED', 'RETRY_COVERED', 'IDENTITY_REQUIRED'])
const epochValue = value => Number.isSafeInteger(value) && value >= 0 ? value : 'OTHER_EPOCH'

export function installRequestDiagnostics(boundary) {
  const original = boundary.assertRequest
  const evidence = { firstThrow: null, firstCurrentHydratingThrow: null, firstUndeclared: null }
  function wrapped(...args) {
    const expected = epochValue(args[0])
    const current = epochValue(boundary.epoch)
    const state = states.has(boundary.state) ? boundary.state : 'OTHER_STATE'
    try { return Reflect.apply(original, this, args) }
    catch (error) {
      try {
        const method = typeof args[1] === 'string' ? args[1].replace(/^\/api\/method\//, '') : ''
        const undeclared = error?.message === 'Current page attempted an undeclared recovery request'
        const kind = undeclared ? 'RECOVERY_UNDECLARED'
          : ['AbortError', 'TypeError', 'SyntaxError', 'Error'].includes(error?.name) ? error.name : 'OTHER_ERROR'
        const locations = typeof error?.stack === 'string'
          ? [...error.stack.matchAll(/(?:src|node_modules)\/[A-Za-z0-9_@./-]+\.(?:js|mjs|cjs|ts|tsx|jsx|vue):\d+:\d+/g)]
            .map(match => match[0]).slice(0, 6) : []
        const entry = { expected, current, state, method: endpoints.has(method) ? method : 'OTHER_ENDPOINT', kind, locations }
        evidence.firstThrow ||= entry
        if (state === 'HYDRATING' && expected === current) evidence.firstCurrentHydratingThrow ||= entry
        if (undeclared) evidence.firstUndeclared ||= entry
      } catch {}
      throw error
    }
  }
  boundary.assertRequest = wrapped
  return { evidence, restore() { if (boundary.assertRequest === wrapped) boundary.assertRequest = original } }
}
