const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')

const source = fs.readFileSync(process.argv[2], 'utf8')
const start = source.indexOf('const systemFilterLabels = {')
const end = source.indexOf('\nconst availableFilters = computed(', start)
assert(start >= 0 && end > start)
const original = [
  { fieldname: 'company_description', label: 'Company Description', value: 'company_description' },
  { fieldname: 'lead_score', label: 'Lead Score', value: 'lead_score' },
  { fieldname: 'last_response_time', label: 'Last Response Time', value: 'last_response_time' },
  { fieldname: 'my_custom_field', label: 'Lead Score', value: 'custom-value' },
  { fieldname: 'lead_owner', label: '自定义负责人名称', value: 'lead_owner' },
  { fieldname: 'last_responded_on', label: '已有服务端翻译', value: 'last_responded_on' },
  { fieldname: 'lead_score', label: 'Lead Score', value: 'custom', is_custom_field: 1 },
]
const messages = { 'Company Description': '公司介绍', 'Lead Score': '线索评分', 'Last Response Time': '最近响应时长' }
const context = {
  props: { doctype: 'CRM Lead' },
  filterableFields: { data: original },
  idFieldDoctypes: ['CRM Lead', 'CRM Deal'],
  computed: (fn) => ({ value: fn() }),
  __: (value) => messages[value] || value,
  h: () => {},
}
const code = source.slice(start, end) + '\nglobalThis.result = filterFieldOptions.value'
vm.runInNewContext(code, context)
assert.deepEqual(Array.from(context.result, (field) => field.label), [
  '公司介绍', '线索评分', '最近响应时长', 'Lead Score', '自定义负责人名称', '已有服务端翻译', 'Lead Score',
])
assert.deepEqual(Array.from(context.result, (field) => field.value), original.map((field) => field.value))
assert.equal(original[0].label, 'Company Description')
const deal = { ...context, props: { doctype: 'CRM Deal' }, result: undefined }
vm.runInNewContext(code, deal)
assert.deepEqual(Array.from(deal.result, (field) => field.label), [
  '公司介绍', 'Lead Score', '最近响应时长', 'Lead Score', '自定义负责人名称', '已有服务端翻译', 'Lead Score',
])
const other = { ...context, props: { doctype: 'Custom DocType' }, result: undefined }
vm.runInNewContext(code, other)
assert.deepEqual(Array.from(other.result, (field) => field.label), original.map((field) => field.label))
console.log('PASS: fixed field labels, custom labels, original values and other doctypes')
