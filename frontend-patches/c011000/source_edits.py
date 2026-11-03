BOUNDARY_IMPORT = "import { accountBoundary } from '../../node_modules/frappe-ui/src/resources/accountBoundary'\n"
SOURCE_EDITS = {
    'frontend/src/data/document.js': [
        ("const documentsCache = {}", "import { accountBoundary } from '../../node_modules/frappe-ui/src/resources/accountBoundary'\nimport { registerResumeDocument, setCreationBaseline } from './safeResume'\nimport { onUnmounted, onMounted, nextTick } from 'vue'\n\nconst documentsCache = {}"),
        ("const intentionallyDeletedDocs = new Set()", "const intentionallyDeletedDocs = new Set()\naccountBoundary.onInvalidate(() => {\n  for (const cache of [documentsCache, controllersCache, assigneesCache, permissionsCache]) {\n    for (const key of Object.keys(cache)) delete cache[key]\n  }\n  intentionallyDeletedDocs.clear()\n})"),
        ("  if (typeof docname === 'number')", "  const resumeEpoch = accountBoundary.epoch\n  if (typeof docname === 'number')"),
        ("      cache: `permissions:${doctype}:${docname}`,\n      auto: docname ? true : false,", "      cache: `permissions:${doctype}:${docname}`,\n      auto: true,"),
        ("  async function setupFormScript() {" , "  const stopResumeDocument = registerResumeDocument(doctype, docname, documentsCache[doctype][docname || ''],\n    () => meta.doctypeMeta.value?.fields || [],\n    () => permissionsCache[doctype]?.[docname || '']?.data)\n  if (vm) {\n    onUnmounted(stopResumeDocument)\n    if (!docname) onMounted(() => nextTick(() => {\n      if (resumeEpoch === accountBoundary.epoch) setCreationBaseline(doctype, documentsCache[doctype]?.[''])\n    }))\n  }\n\n  async function setupFormScript() {\n    if (resumeEpoch !== accountBoundary.epoch || accountBoundary.state !== 'ACTIVE') return"),
        ("    if (!controllersArray || controllersArray.length === 0) return", "    if (resumeEpoch !== accountBoundary.epoch || accountBoundary.state !== 'ACTIVE') return\n    if (!controllersArray || controllersArray.length === 0) return"),
        ("    const linkValues = await fetchLinkValues(linkDf.options, value, sources)", "    const linkValues = await fetchLinkValues(linkDf.options, value, sources)\n    accountBoundary.assertActive(resumeEpoch)"),
        ("  async function triggerOnChange(fieldname, _value, row) {", "  async function triggerOnChange(fieldname, _value, row) {\n    accountBoundary.assertActive(resumeEpoch)"),
        ("  async function trigger(taskFn, row = null) {", "  async function trigger(taskFn, row = null) {\n    accountBoundary.assertActive(resumeEpoch)"),
        ("  function setFieldHtml(fieldname, html) {", "  function setFieldHtml(fieldname, html) {\n    accountBoundary.assertActive(resumeEpoch)"),
        ("  function getControllers(row = null) {", "  function getControllers(row = null) {\n    if (resumeEpoch !== accountBoundary.epoch) return []"),
    ],
    'frontend/src/stores/meta.js': [
        ("const doctypesMeta = reactive({})", BOUNDARY_IMPORT + "\nconst doctypesMeta = reactive({})"),
        ("const userSettings = reactive({})", "const userSettings = reactive({})\naccountBoundary.onInvalidate(() => {\n  for (const cache of [doctypesMeta, userSettings]) {\n    for (const key of Object.keys(cache)) delete cache[key]\n  }\n})"),
    ],
    'frontend/src/data/script.js': [
        ("const doctypeScripts = reactive({})", BOUNDARY_IMPORT + "\nconst doctypeScripts = reactive({})"),
        ("const fileScriptCache = {}", "const fileScriptCache = {}\naccountBoundary.onInvalidate(() => {\n  for (const cache of [doctypeScripts, fileScriptCache]) {\n    for (const key of Object.keys(cache)) delete cache[key]\n  }\n})"),
        ("async function loadFileScript(doctype, view) {", "async function loadFileScript(doctype, view) {\n  const resumeEpoch = accountBoundary.epoch"),
        ("    fileScriptCache[key] = await loader()", "    const loaded = await loader()\n    if (resumeEpoch !== accountBoundary.epoch) return null\n    fileScriptCache[key] = loaded"),
        ("  async function setupScript(document, helpers = {}) {",  "  async function setupScript(document, helpers = {}) {\n    const resumeEpoch = accountBoundary.epoch"),
        ("    const { $dialog, $socket } = globalStore()", "    accountBoundary.assertActive(resumeEpoch)\n    const { $dialog, $socket } = globalStore()"),
    ],
    'frontend/src/components/ViewControls.vue': [
        ("<script setup>", "<script setup>\nimport { registerResumePage } from '@/data/safeResume'"),
        ("list.value = listResource", "const stopResumePage = registerResumePage(route.name, () => listResource.params || getParams())\nonBeforeUnmount(stopResumePage)\nlist.value = listResource"),
    ],
    'frontend/src/pages/Lead.vue': [
        ("<script setup>", "<script setup>\nimport { registerResumePage } from '@/data/safeResume'\nimport { onUnmounted as resumeUnmounted } from 'vue'"),
        ("</script>", "const stopResumePage = registerResumePage(route.name)\nresumeUnmounted(stopResumePage)\n</script>"),
    ],
    'frontend/src/pages/Deal.vue': [
        ("<script setup>", "<script setup>\nimport { registerResumePage } from '@/data/safeResume'\nimport { onUnmounted as resumeUnmounted } from 'vue'"),
        ("</script>", "const stopResumePage = registerResumePage(route.name)\nresumeUnmounted(stopResumePage)\n</script>"),
    ],
    'frontend/src/pages/Leads.vue': [
        ("<script setup>", "<script setup>\nimport { reopenCreation } from '@/data/safeResume'"),
        ("const showLeadModal = ref(false)", "const showLeadModal = ref(reopenCreation('CRM Lead'))"),
    ],
    'frontend/src/pages/Deals.vue': [
        ("<script setup>", "<script setup>\nimport { reopenCreation } from '@/data/safeResume'"),
        ("const showDealModal = ref(false)", "const showDealModal = ref(reopenCreation('CRM Deal'))"),
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


def transform(target, data):
    text = data.decode('utf-8')
    for old, new in SOURCE_EDITS[target]:
        if text.count(old) != 1:
            raise ValueError('Resume source anchor mismatch: ' + target)
        text = text.replace(old, new)
    return text.encode('utf-8')
