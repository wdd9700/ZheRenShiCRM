BOUNDARY_IMPORT = "import { accountBoundary } from '../../node_modules/frappe-ui/src/resources/accountBoundary'\n"
SOURCE_EDITS = {
    'frontend/src/data/document.js': [
        ("const documentsCache = {}", "import { accountBoundary } from '../../node_modules/frappe-ui/src/resources/accountBoundary'\nimport { registerResumeDocument, setCreationBaseline } from './safeResume'\nimport { onUnmounted, onMounted, nextTick } from 'vue'\n\nconst documentsCache = {}"),
        ("const intentionallyDeletedDocs = new Set()", "const intentionallyDeletedDocs = new Set()\naccountBoundary.onInvalidate(() => {\n  for (const cache of [documentsCache, controllersCache, assigneesCache, permissionsCache]) {\n    for (const key of Object.keys(cache)) delete cache[key]\n  }\n  intentionallyDeletedDocs.clear()\n})"),
        ("  if (typeof docname === 'number')", "  const resumeEpoch = accountBoundary.epoch\n  if (typeof docname === 'number')"),
        ("      url: 'frappe.client.get_doc_permissions',", "      url: docname ? 'frappe.client.get_doc_permissions' : 'frappe.client.has_permission',\n      transform: data => docname ? data : { permissions: { create: data.has_permission } },"),
        ("      cache: `permissions:${doctype}:${docname}`,\n      auto: docname ? true : false,", "      cache: `permissions:${doctype}:${docname}`,\n      auto: true,"),
        ("      initialData: { permissions: {} },", "      initialData: { permissions: {} },"),
        ("        docname: docname,\n      },\n      initialData:", "        docname: docname || '',\n        ...(!docname ? { perm_type: 'create' } : {}),\n      },\n      initialData:"),
        ("  async function setupFormScript() {" , "  const stopResumeDocument = registerResumeDocument(doctype, docname, documentsCache[doctype][docname || ''],\n    () => meta.doctypeMeta.value?.fields || [],\n    () => permissionsCache[doctype]?.[docname || '']?.data)\n  if (vm) {\n    onUnmounted(stopResumeDocument)\n    if (!docname) onMounted(() => nextTick(() => {\n      if (resumeEpoch === accountBoundary.epoch) setCreationBaseline(doctype, documentsCache[doctype]?.[''])\n    }))\n  }\n\n  async function setupFormScript(runLifecycle = true) {\n    if (resumeEpoch !== accountBoundary.epoch || accountBoundary.state !== 'ACTIVE') return"),
        ("    if (!controllersArray || controllersArray.length === 0) return", "    if (resumeEpoch !== accountBoundary.epoch || accountBoundary.state !== 'ACTIVE') return\n    if (!controllersArray || controllersArray.length === 0) return"),
        ("    const linkValues = await fetchLinkValues(linkDf.options, value, sources)", "    const linkValues = await fetchLinkValues(linkDf.options, value, sources)\n    accountBoundary.assertActive(resumeEpoch)"),
        ("  async function triggerOnChange(fieldname, _value, row) {", "  async function triggerOnChange(fieldname, _value, row) {\n    accountBoundary.assertActive(resumeEpoch)"),
        ("  async function trigger(taskFn, row = null) {", "  async function trigger(taskFn, row = null) {\n    accountBoundary.assertActive(resumeEpoch)\n    if (!controllersCache[doctype]?.[docname || '']) await setupFormScript(false)\n    accountBoundary.assertActive(resumeEpoch)"),
        ("    triggerOnLoad()\n    triggerOnRender()", "    if (runLifecycle) { notifyHook(triggerOnLoad); notifyHook(triggerOnRender) }"),
        ("onSuccess: async () => await setupFormScript(),", "onSuccess: () => notifyHook(setupFormScript),"),
        ("              triggerOnSave()", "              notifyHook(triggerOnSave)"),
        ("              triggerOnError(err)", "              notifyHook(() => triggerOnError(err))"),
        ("      setupFormScript()", "      notifyHook(setupFormScript)"),
        ("  async function triggerOnLoad() {", "  function notifyHook(hook) {\n    void Promise.resolve().then(() => {\n      accountBoundary.assertActive(resumeEpoch)\n      return hook()\n    }).catch(() => {\n      try { accountBoundary.assertActive(resumeEpoch) } catch { return }\n      toast.error(__('An error occurred while running the document script'))\n    }).catch(() => {})\n  }\n\n  async function triggerOnLoad() {"),
        ("  function setFieldHtml(fieldname, html) {", "  function setFieldHtml(fieldname, html) {\n    accountBoundary.assertActive(resumeEpoch)"),
        ("  function getControllers(row = null) {", "  function getControllers(row = null) {\n    if (resumeEpoch !== accountBoundary.epoch) return []"),
    ],
    'frontend/src/stores/meta.js': [
        ("const doctypesMeta = reactive({})", BOUNDARY_IMPORT + "\nlet doctypesMeta = reactive({})"),
        ("const userSettings = reactive({})", "let userSettings = reactive({})\nfunction currentMetaScope() { return { doctypesMeta, userSettings } }\naccountBoundary.onInvalidate(() => {\n  for (const cache of [doctypesMeta, userSettings]) {\n    for (const key of Object.keys(cache)) delete cache[key]\n  }\n  doctypesMeta = reactive({}); userSettings = reactive({})\n})"),
        ("export function getMeta(doctype) {", "export function getMeta(doctype) {\n  const resumeEpoch = accountBoundary.epoch\n  const { doctypesMeta, userSettings } = currentMetaScope()"),
        ("  function saveUserSettings(parentDoctype, key, value, callback) {", "  function saveUserSettings(parentDoctype, key, value, callback) {\n    if (accountBoundary.state === 'HYDRATING') return\n    accountBoundary.assertActive(resumeEpoch)"),
    ],
    'frontend/src/data/script.js': [
        ("const doctypeScripts = reactive({})", BOUNDARY_IMPORT + "\nconst doctypeScripts = reactive({})"),
        ("const fileScriptCache = {}", "const fileScriptCache = {}\naccountBoundary.onInvalidate(() => {\n  for (const cache of [doctypeScripts, fileScriptCache]) {\n    for (const key of Object.keys(cache)) delete cache[key]\n  }\n})"),
        ("async function loadFileScript(doctype, view) {", "async function loadFileScript(doctype, view) {\n  const resumeEpoch = accountBoundary.epoch"),
        ("    fileScriptCache[key] = await loader()", "    const loaded = await loader()\n    if (resumeEpoch !== accountBoundary.epoch) return null\n    fileScriptCache[key] = loaded"),
        ("export function getScript(doctype, view = 'Form') {", "export function getScript(doctype, view = 'Form') {\n  const resumeEpoch = accountBoundary.epoch"),
        ("  async function setupScript(document, helpers = {}) {",  "  async function setupScript(document, helpers = {}) {\n    accountBoundary.assertActive(resumeEpoch)"),
        ("    const { $dialog, $socket } = globalStore()", "    accountBoundary.assertActive(resumeEpoch)\n    const { $dialog, $socket } = globalStore()"),
    ],
    'frontend/src/components/ViewControls.vue': [
        ("<script setup>", "<script setup>\nimport { registerResumePage, resumeListParams } from '@/data/safeResume'"),
        ("  params: getParams(),", "  params: resumeListParams(props.doctype, getParams()),"),
        ("const initialParams = getParams()", "const initialParams = resumeListParams(props.doctype, getParams())"),
        ("list.value = listResource", "let stopResumePage = () => {}\nonMounted(() => { stopResumePage = registerResumePage(route.name, () => listResource.params || getParams()) })\nonBeforeUnmount(() => stopResumePage())\nlist.value = listResource"),
    ],
    'frontend/src/pages/Lead.vue': [
        ("<script setup>", "<script setup>\nimport { registerResumePage } from '@/data/safeResume'\nimport { onUnmounted as resumeUnmounted, onMounted as resumeMounted } from 'vue'"),
        ("</script>", "let stopResumePage = () => {}\nresumeMounted(() => { stopResumePage = registerResumePage(route.name) })\nresumeUnmounted(() => stopResumePage())\n</script>"),
    ],
    'frontend/src/pages/Deal.vue': [
        ("<script setup>", "<script setup>\nimport { registerResumePage } from '@/data/safeResume'\nimport { onUnmounted as resumeUnmounted, onMounted as resumeMounted } from 'vue'"),
        ("</script>", "let stopResumePage = () => {}\nresumeMounted(() => { stopResumePage = registerResumePage(route.name) })\nresumeUnmounted(() => stopResumePage())\n</script>"),
    ],
    'frontend/src/pages/Leads.vue': [
        ("<script setup>", "<script setup>\nimport { reopenCreation } from '@/data/safeResume'"),
        ("const showLeadModal = ref(false)", "const showLeadModal = ref(reopenCreation('CRM Lead'))"),
    ],
    'frontend/src/pages/Deals.vue': [
        ("<script setup>", "<script setup>\nimport { reopenCreation } from '@/data/safeResume'"),
        ("const showDealModal = ref(false)", "const showDealModal = ref(reopenCreation('CRM Deal'))"),
    ],
    'frontend/src/stores/notifications.js': [
        ("export const notifications = createResource({", BOUNDARY_IMPORT + "\nfunction freshNotifications() { return createResource({"),
        ("  auto: true,\n})", "  auto: true,\n}) }\nexport let notifications = freshNotifications()\naccountBoundary.onInvalidate(() => { visible.value = false })\naccountBoundary.onHydrate(() => { notifications = freshNotifications() })"),
    ],
    'frontend/src/stores/settings.js': [
        ("const _settings = createDocumentResource({", BOUNDARY_IMPORT + "\nfunction freshSettings() { return createDocumentResource({"),
        ("})\n\nexport function getSettings()", "}) }\nlet _settings = freshSettings()\naccountBoundary.onInvalidate(() => {\n  settings.value = {}\n  for (const key of Object.keys(brand)) delete brand[key]\n})\naccountBoundary.onHydrate(() => { _settings = freshSettings() })\n\nexport function getSettings()"),
    ],
    'frontend/src/composables/telephony.js': [
        ("createResource({", BOUNDARY_IMPORT + "\nfunction refreshTelephony() { return createResource({"),
        ("})\n\nexport function setEnabled", "}) }\nrefreshTelephony()\naccountBoundary.onInvalidate(() => { integrations.value = {}; defaultCallingMedium.value = ''; callEnabled.value = false })\naccountBoundary.onHydrate(refreshTelephony)\n\nexport function setEnabled"),
    ],
    'frontend/src/composables/whatsapp.js': [
        ("export const whatsappEnabled", BOUNDARY_IMPORT + "\nexport const whatsappEnabled"),
        ("createResource({\n  url: 'crm.api.whatsapp.is_whatsapp_enabled'", "function refreshWhatsapp() {\ncreateResource({\n  url: 'crm.api.whatsapp.is_whatsapp_enabled'"),
        ("    isWhatsappInstalled.value = Boolean(data)\n  },\n})", "    isWhatsappInstalled.value = Boolean(data)\n  },\n})\n}\nrefreshWhatsapp()\naccountBoundary.onInvalidate(() => { whatsappEnabled.value = false; isWhatsappInstalled.value = false })\naccountBoundary.onHydrate(refreshWhatsapp)"),
    ],
    'frontend/src/composables/erpnext.js': [
        ("createResource({", BOUNDARY_IMPORT + "\nfunction refreshQuotations() { return createResource({"),
        ("    canViewQuotations.value = Boolean(data)\n  },\n})", "    canViewQuotations.value = Boolean(data)\n  },\n}) }\nrefreshQuotations()\naccountBoundary.onInvalidate(() => { canViewQuotations.value = false })\naccountBoundary.onHydrate(refreshQuotations)"),
    ],
    'frontend/src/composables/useCommandPalette.js': [
        ("let previousFocus = null", BOUNDARY_IMPORT + "\nlet previousFocus = null\naccountBoundary.onInvalidate(() => {\n  commandPaletteOpen.value = false; commandPaletteQuery.value = ''\n  commandProvider.value = () => []; contextualProvider.value = () => []; stack.value = []\n  commandPaletteLoading.value = false; commandPaletteSearching.value = false; previousFocus = null\n})"),
        ("async function openChildren(command) {", "async function openChildren(command) {\n  const epoch = accountBoundary.epoch"),
        ("    const commands = checkedFirst(await command.children())", "    const commands = checkedFirst(await command.children())\n    accountBoundary.assertActive(epoch)"),
    ],
    'frontend/node_modules/frappe-ui/src/utils/frappeRequest.ts': [
        ("import { getConfig }", "import { accountBoundary } from '../resources/accountBoundary'\nimport { getConfig }"),
        ("  return request<TResponse>({", "  const promise = request<TResponse>({"),
        ("  })\n}", "  })\n  accountBoundary.track(promise)\n  return promise\n}"),
        ("        credentials,", "        credentials,\n        cache: 'no-store',"),
        ("  const originalOptions = options", "  const resumeEpoch = accountBoundary.epoch\n  const authAction = ['login', 'logout', '/api/method/login', '/api/method/logout'].includes(options.url || '')\n  const assertResume = () => { if (!authAction) accountBoundary.assertRequest(resumeEpoch, options.url) }\n  assertResume()\n  const originalOptions = options"),
        ("    transformRequest: (options) => {", "    transformRequest: (options) => {\n      assertResume()"),
        ("    transformResponse: async (response, options) => {", "    transformResponse: async (response, options) => {\n      assertResume()"),
        ("        const data = (await response.json()) as FrappeResponseBody", "        const data = (await response.json()) as FrappeResponseBody\n        assertResume()"),
        ("        let errorResponse = await response.text()", "        let errorResponse = await response.text()\n        assertResume()"),
        ("    transformError: (error) => {", "    transformError: (error) => {\n      assertResume()"),
    ],
}


for target, anchor, reset in [
    ('frontend/src/composables/doctypeModal.js', 'const callbacks = ref({})',
     "show.value = false; doctype.value = ''; name.value = ''; title.value = ''; defaults.value = {}; callbacks.value = {}"),
    ('frontend/src/composables/document.js', 'export const createDocumentCallback = ref(null)',
     "showCreateDocumentModal.value = false; createDocumentDoctype.value = ''; createDocumentData.value = {}; createDocumentCallback.value = null"),
    ('frontend/src/composables/noteView.ts', 'const linkedTitles = reactive<Record<string, string>>({})',
     'show.value = false; note.value = null; onEdit.value = null; for (const key of Object.keys(linkedTitles)) delete linkedTitles[key]'),
    ('frontend/src/utils/renderFieldLayoutDialog.js', 'export const fieldLayoutDialogs = ref([])',
     'fieldLayoutDialogs.value = []'),
    ('frontend/src/utils/dialogs.jsx', 'let dialogs = ref([])', 'dialogs.value = []'),
    ('frontend/src/composables/modals.js', 'export const setupFeedback = ref(null)',
     'showQuickEntryModal.value = false; quickEntryProps.value = {}; showAboutModal.value = false; showChangePasswordModal.value = false; setupFeedback.value = null'),
]:
    SOURCE_EDITS[target] = [(anchor, BOUNDARY_IMPORT + '\n' + anchor + '\n' +
        'function resetResumeState() { ' + reset + ' }\n' +
        "accountBoundary.onInvalidate(() => { if (accountBoundary.state === 'IDENTITY_REQUIRED') resetResumeState() })\n" +
        'accountBoundary.onHydrate(resetResumeState)')]

SOURCE_EDITS['frontend/src/utils/dialogs.jsx'] += [
    ('export function createDialog(dialogOptions) {', 'export function createDialog(dialogOptions) {\n  const epoch = accountBoundary.epoch'),
    ('    dialog.show = true', '    if (epoch === accountBoundary.epoch) dialog.show = true'),
]


SOURCE_EDITS['frontend/src/composables/useVisitedRecords.ts'] = [
    ("import { call }", BOUNDARY_IMPORT + "import { call }"),
    ('    if (!name) return', "    if (!name || accountBoundary.state !== 'ACTIVE') return"),
]
SOURCE_EDITS['frontend/src/components/Layouts/AppSidebar.vue'] = [
    ('<script setup>', "<script setup>\nimport { accountBoundary } from '../../../node_modules/frappe-ui/src/resources/accountBoundary'"),
    ('  if (props.mobile) return', "  if (props.mobile || accountBoundary.state === 'HYDRATING') return"),
]


SOURCE_EDITS['frontend/src/components/Activities/Activities.vue'] = [
    ('<script setup>', "<script setup>\nimport { registerResumeSection } from '@/data/safeResume'\nimport { onMounted as resumeMounted, onUnmounted as resumeUnmounted } from 'vue'"),
    ('</script>', "let stopResumeSection = () => {}\nresumeMounted(() => { stopResumeSection = registerResumeSection('activity:' + props.docname) })\nresumeUnmounted(() => stopResumeSection())\n</script>"),
]


SOURCE_EDITS['frontend/src/stores/users.js'] = [
    ("import { defineStore }", BOUNDARY_IMPORT + "import { defineStore }"),
    ("  const session = sessionStore()", "  const session = sessionStore()\n  const resumeEpoch = accountBoundary.epoch"),
    ('  let flushScheduled = false', "  let flushScheduled = false\n  const stopResume = accountBoundary.onInvalidate(() => {\n    for (const key of Object.keys(usersByName)) delete usersByName[key]\n    pendingResolves.clear(); stopResume()\n  })"),
    ('    const fire = () => usersFull.fetch()', '    const fire = () => { if (resumeEpoch === accountBoundary.epoch) usersFull.fetch() }'),
    ('  async function flush() {', '  async function flush() {\n    if (resumeEpoch !== accountBoundary.epoch) return'),
    ('      const records = await r.fetch()', '      const records = await r.fetch()\n      if (resumeEpoch !== accountBoundary.epoch) return'),
    ('  function getUser(email) {', '  function getUser(email) {\n    if (resumeEpoch !== accountBoundary.epoch) return {}'),
]
SOURCE_EDITS['frontend/src/stores/views.js'] = [
    ("import { defineStore }", BOUNDARY_IMPORT + "import { defineStore }"),
    ('  const defaultViews = reactive({})', '  const defaultViews = reactive({})\n  const stopResume = accountBoundary.onInvalidate(() => {\n    for (const cache of [viewsByName, standardViews.value, defaultViews]) {\n      for (const key of Object.keys(cache)) delete cache[key]\n    }\n    pinnedViews.value.length = 0; publicViews.value.length = 0; stopResume()\n  })'),
]


SOURCE_EDITS['frontend/src/components/CommunicationArea.vue'] = [
    ('<script setup>', "<script setup>\nimport { registerUnsavedEditor } from '@/data/safeResume'\nimport { onUnmounted as resumeUnmounted } from 'vue'"),
    ("const newEmail = useStorage(\n  `emailBoxContent-${getUser().email}-${props.doctype}-${doc.value.name}`,\n  '',\n)", "const newEmail = ref('')"),
    ("// A restored draft already carries its signature; this flag (persisted with the\n// draft) stops setSignature from prepending another one on every reopen/reload.\nconst signatureAdded = useStorage(\n  `emailSignatureAdded-${getUser().email}-${props.doctype}-${doc.value.name}`,\n  false,\n)", 'const signatureAdded = ref(false)'),
    ("const newComment = useStorage(\n  `commentBoxContent-${getUser().email}-${props.doctype}-${doc.value.name}`,\n  '',\n)", "const newComment = ref('')"),
    ("const attachments = useStorage(\n  `attachments-${getUser().email}-${props.doctype}-${doc.value.name}`,\n  [],\n  localStorage,\n  {\n    serializer: {\n      read: (v) => (v ? JSON.parse(v) : []),\n      write: (v) => JSON.stringify(v),\n    },\n  },\n)", "const attachments = ref([])\nconst stopUnsavedEditor = registerUnsavedEditor(\n  () => showEmailBox.value || showCommentBox.value || !isContentEmpty(newEmail.value) || !isContentEmpty(newComment.value) || attachments.value.length > 0 ||\n    Boolean(newEmailEditor.value?.ccEmails?.length || newEmailEditor.value?.bccEmails?.length) ||\n    (newEmailEditor.value && (newEmailEditor.value.subject !== subject.value ||\n      JSON.stringify(newEmailEditor.value.toEmails) !== JSON.stringify(doc.value.email ? [doc.value.email] : []))),\n  () => { newEmail.value = ''; newComment.value = ''; signatureAdded.value = false; attachments.value = []; newEmailEditor.value = null; newCommentEditor.value = null; showEmailBox.value = false; showCommentBox.value = false },\n)\nresumeUnmounted(stopUnsavedEditor)"),
]


for kind in ['Lead', 'Deal']:
    lower = kind.lower()
    resource = lower + 'StatusResource'
    SOURCE_EDITS[f'frontend/src/components/Modals/{kind}Modal.vue'] = [
        (f'const {{ get{kind}Status, statusOptions }} = statusesStore()',
         f'const {{ get{kind}Status, statusOptions, {lower}Statuses: {resource} }} = statusesStore()'),
        ("  params: { doctype: 'CRM " + kind + "', type: 'Quick Entry' },\n  auto: true,",
         "  params: { doctype: 'CRM " + kind + "', type: 'Quick Entry' },\n  auto: false,"),
        (f'field.prefix = get{kind}Status({lower}.doc.status).color',
         f'field.prefix = {resource}.data?.length ? get{kind}Status({lower}.doc.status)?.color : undefined'),
    ]
    if kind == 'Lead':
        SOURCE_EDITS[f'frontend/src/components/Modals/{kind}Modal.vue'].append(
            ("import { computed, onMounted, ref, nextTick } from 'vue'",
             "import { computed, onMounted, ref, nextTick, watch } from 'vue'"))
    else:
        SOURCE_EDITS[f'frontend/src/components/Modals/{kind}Modal.vue'].append(
            ('if (!deal.doc.status && dealStatuses.value[0].value)',
             'if (!deal.doc.status && dealStatuses.value[0]?.value)'))
    anchor = 'const createLead = createResource({' if kind == 'Lead' else 'async function createDeal() {'
    SOURCE_EDITS[f'frontend/src/components/Modals/{kind}Modal.vue'].append(
        (anchor, f"watch(() => {resource}.list.fetched, (fetched) => {{\n  if (fetched) tabs.fetch()\n}}, {{ immediate: true }})\n\n" + anchor))


def transform(target, data):
    text = data.decode('utf-8')
    for old, new in SOURCE_EDITS[target]:
        if text.count(old) != 1:
            raise ValueError('Resume source anchor mismatch: ' + target)
        text = text.replace(old, new)
    return text.encode('utf-8')
