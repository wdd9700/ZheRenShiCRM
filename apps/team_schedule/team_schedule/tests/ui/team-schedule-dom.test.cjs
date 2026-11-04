'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {init} = require('../../public/team-schedule.js');
const {createDom, fire, flush, jsonResponse, deferred} = require('./dom-stub.cjs');

const html = fs.readFileSync(path.join(__dirname, '../../www/team-schedule.html'), 'utf8');

function setup(fetchImpl) {
  const environment = createDom(html, fetchImpl);
  init(environment.document, environment.window);
  return environment;
}

function methodCalls(calls, suffix) {
  return calls.filter(call => call.url.endsWith(suffix));
}

function setValues(document, values) {
  for (const [id, value] of Object.entries(values)) document.getElementById(id).value = value;
}

test('init list operation cannot cross visibility clear and rebind a new epoch', async () => {
  const calls = [];
  const endResolution = deferred();
  let resolutions = 0;
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push({url, payload});
    if (url.endsWith('.resolve_local')) {
      resolutions += 1;
      if (resolutions === 2) return endResolution.promise;
      return jsonResponse({message: {utc: '2026-11-01T09:00:00Z', timezone: 'UTC', offset_minutes: 0}});
    }
    if (url.endsWith('.list')) return jsonResponse({message: {items: [{name: 'must-not-return'}], next_cursor: null}});
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {
    'list-start': '2026-11-01T09:00',
    'list-end': '2026-11-02T09:00',
    'list-timezone': 'UTC'
  });
  const pending = fire(environment.document.getElementById('list-form'), 'submit');
  await flush();
  assert.equal(methodCalls(calls, '.resolve_local').length, 2);
  await fire(environment.document, 'visibilitychange');
  endResolution.resolve(jsonResponse({message: {utc: '2026-11-02T09:00:00Z', timezone: 'UTC', offset_minutes: 0}}));
  await pending;
  assert.equal(methodCalls(calls, '.list').length, 0);
  assert.equal(environment.document.getElementById('schedule-list').children.length, 0);
  assert.doesNotMatch(environment.document.getElementById('list-status').textContent, /已加载1条/);
  assert.match(environment.document.getElementById('session-status').textContent, /已清除/);
});

test('init invalidates between local resolutions without issuing the end request', async () => {
  const calls = [];
  const startResolution = deferred();
  const environment = setup(async (url, options) => {
    calls.push({url, payload: JSON.parse(options.body)});
    if (url.endsWith('.resolve_local')) return startResolution.promise;
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {
    'list-start': '2026-11-01T09:00',
    'list-end': '2026-11-02T09:00',
    'list-timezone': 'UTC'
  });
  const pending = fire(environment.document.getElementById('list-form'), 'submit');
  await flush();
  await fire(environment.document, 'visibilitychange');
  startResolution.resolve(jsonResponse({message: {utc: '2026-11-01T09:00:00Z', timezone: 'UTC', offset_minutes: 0}}));
  await pending;
  assert.equal(methodCalls(calls, '.resolve_local').length, 1);
  assert.equal(methodCalls(calls, '.list').length, 0);
});

test('Framework 403 clears sensitive edit form through actual init failure handling', async () => {
  const environment = setup(async () => jsonResponse({exc_type: 'PermissionError', _server_messages: '[]'}, false, 403));
  setValues(environment.document, {
    'editing-name': 'private-schedule-id',
    'editing-revision': '7',
    'schedule-title': 'private title',
    'schedule-description': 'private description',
    'viewer-user': 'viewer@example.test'
  });
  await fire(environment.document.getElementById('grant-form'), 'submit');
  assert.equal(environment.document.getElementById('editing-name').value, '');
  assert.equal(environment.document.getElementById('editing-revision').value, '');
  assert.equal(environment.document.getElementById('schedule-title').value, '');
  assert.equal(environment.document.getElementById('schedule-description').value, '');
  assert.match(environment.document.getElementById('grant-status').textContent, /Framework拒绝/);
  assert.match(environment.document.getElementById('session-status').textContent, /敏感草稿已清除/);
});

test('Framework non-envelope 417 also clears sensitive edit form without claiming a specific identity cause', async () => {
  const environment = setup(async () => jsonResponse({exc_type: 'ValidationError', _server_messages: '[]'}, false, 417));
  setValues(environment.document, {
    'editing-name': 'private-schedule-id',
    'editing-revision': '8',
    'schedule-title': 'private title',
    'schedule-description': 'private description',
    'viewer-user': 'viewer@example.test'
  });
  await fire(environment.document.getElementById('grant-form'), 'submit');
  assert.equal(environment.document.getElementById('editing-name').value, '');
  assert.equal(environment.document.getElementById('schedule-title').value, '');
  assert.equal(environment.document.getElementById('schedule-description').value, '');
  assert.match(environment.document.getElementById('grant-status').textContent, /Framework拒绝/);
  assert.doesNotMatch(environment.document.getElementById('grant-status').textContent, /登录已失效|身份错误/);
});

test('explicit application 417 remains a business error and does not claim identity failure', async () => {
  const environment = setup(async () => jsonResponse({message: {error: {code: 'INVALID_INPUT'}}}, false, 417));
  setValues(environment.document, {
    'editing-name': 'draft-id',
    'editing-revision': '3',
    'schedule-title': 'draft title',
    'schedule-description': 'draft description',
    'viewer-user': 'not-a-user'
  });
  await fire(environment.document.getElementById('grant-form'), 'submit');
  assert.equal(environment.document.getElementById('editing-name').value, 'draft-id');
  assert.equal(environment.document.getElementById('schedule-title').value, 'draft title');
  assert.equal(environment.document.getElementById('schedule-description').value, 'draft description');
  assert.match(environment.document.getElementById('grant-status').textContent, /输入不符合要求/);
  assert.doesNotMatch(environment.document.getElementById('grant-status').textContent, /登录已失效|身份错误/);
});

async function verifyLongSchedule(endLocal, availability, expectedWindows) {
  const calls = [];
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push({url, payload});
    if (url.endsWith('.resolve_local')) return jsonResponse({message: {utc: payload.local + ':00Z', timezone: payload.timezone, offset_minutes: 0}});
    if (url.endsWith('availability.api.query')) return jsonResponse({message: {busy: [{user: 'owner@example.test', intervals: []}], common_free: [], display_timezone: 'UTC'}});
    if (url.endsWith('.create')) {
      return jsonResponse({message: {schedule: {
        name: 'long-schedule', owner: 'owner@example.test', title: payload.title, description: payload.description,
        start_utc: payload.start_utc, end_utc: payload.end_utc, source_timezone: payload.source_timezone,
        status: 'Active', availability: payload.availability, revision: 1, members: []
      }}});
    }
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {
    'schedule-title': 'long ' + availability,
    'schedule-description': '',
    'schedule-start': '2026-11-01T09:07',
    'schedule-end': endLocal,
    'schedule-timezone': 'UTC',
    'schedule-availability': availability
  });
  await fire(environment.document.getElementById('schedule-form'), 'submit');
  const queries = methodCalls(calls, 'availability.api.query');
  assert.equal(queries.length, expectedWindows);
  for (let index = 0; index < queries.length; index += 1) {
    const payload = queries[index].payload;
    assert.ok(Date.parse(payload.end_utc) - Date.parse(payload.start_utc) <= 7 * 86400000);
    if (index) assert.equal(payload.start_utc, queries[index - 1].payload.end_utc);
  }
  const creates = methodCalls(calls, '.create');
  assert.equal(creates.length, 1);
  assert.equal(creates[0].payload.availability, availability);
  assert.equal(creates[0].payload.end_utc, endLocal + ':00Z');
}

test('init saves an 8-day Free schedule after two complete busy checks', async () => {
  await verifyLongSchedule('2026-11-09T09:42', 'Free', 2);
});

test('init saves a 31-day schedule after five complete busy checks', async () => {
  await verifyLongSchedule('2026-12-02T09:07', 'Busy', 5);
});

test('existing ICS source continues same-origin update and cancel without duplicate creation', async () => {
  const calls = [];
  const created = [];
  let stage = 0;
  const sourceId = 'source-existing-001';
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push({url, payload});
    if (url.endsWith('.create_source')) return jsonResponse({message: {source_id: sourceId}});
    if (url.endsWith('.preview')) {
      stage += 1;
      const action = ['create', 'update', 'cancel'][stage - 1];
      return jsonResponse({message: {
        receipt: 'receipt-' + stage,
        expires_in: 900,
        items: [{
          index: 0, action, code: null, allowed_resolutions: [], expected_revision: null,
          preview: {
            title: 'source event', description: 'version ' + stage,
            start_utc: '2026-11-04T09:07:00Z', end_utc: '2026-11-04T09:42:00Z',
            source_timezone: 'UTC', status: action === 'cancel' ? 'Cancelled' : 'Active', availability: 'Busy'
          }
        }]
      }});
    }
    if (url.endsWith('.apply')) {
      const result = ['create', 'update', 'cancel'][stage - 1];
      if (result === 'create') created.push('schedule-1');
      return jsonResponse({message: {items: [{index: 0, result, code: null, schedule_name: 'schedule-1', revision: stage}]}});
    }
    throw new Error('unexpected request ' + url);
  });

  async function selectFile(version) {
    const bytes = new TextEncoder().encode('BEGIN:VCALENDAR\r\nVERSION:' + version + '\r\nEND:VCALENDAR\r\n');
    const input = environment.document.getElementById('ics-file');
    input.files = [{size: bytes.length, arrayBuffer: async () => bytes.buffer}];
    await fire(input, 'change');
  }

  async function previewAndApply(version) {
    await selectFile(version);
    await environment.document.getElementById('ics-preview').click();
    const confirm = environment.document.getElementById('ics-confirm');
    confirm.checked = true;
    await fire(confirm, 'change');
    await environment.document.getElementById('ics-apply').click();
  }

  setValues(environment.document, {'source-label': 'local source'});
  await fire(environment.document.getElementById('source-form'), 'submit');
  assert.equal(environment.document.getElementById('existing-source-id').value, sourceId);
  await previewAndApply('1');

  for (const version of ['2', '3']) {
    await fire(environment.document, 'visibilitychange');
    assert.equal(environment.document.getElementById('existing-source-id').value, '');
    setValues(environment.document, {'existing-source-id': sourceId});
    await fire(environment.document.getElementById('existing-source-form'), 'submit');
    await previewAndApply(version);
  }

  assert.equal(created.length, 1);
  assert.equal(methodCalls(calls, '.create_source').length, 1);
  assert.equal(methodCalls(calls, '.preview').length, 3);
  assert.equal(methodCalls(calls, '.apply').length, 3);
  for (const call of [...methodCalls(calls, '.preview'), ...methodCalls(calls, '.apply')]) assert.equal(call.payload.source_id, sourceId);
  assert.deepEqual(methodCalls(calls, '.apply').map(call => call.payload.confirm), [true, true, true]);
});

test('init renders literal HTML in ICS text without creating executable elements or fetching URLs', async () => {
  const calls = [];
  const literalTitle = '<script>globalThis.compromised = true</script>';
  const literalDescription = '<img src="https://invalid.example/private-canary" onerror="globalThis.compromised = true">';
  const environment = setup(async (url, options) => {
    calls.push({url, payload: JSON.parse(options.body)});
    if (url.endsWith('.create_source')) return jsonResponse({message: {source_id: 'literal-source'}});
    if (url.endsWith('.preview')) {
      return jsonResponse({message: {
        receipt: 'literal-receipt', expires_in: 900,
        items: [{
          index: 0, action: 'create', code: null, allowed_resolutions: [], expected_revision: null,
          preview: {
            title: literalTitle, description: literalDescription,
            start_utc: '2026-11-04T09:07:00Z', end_utc: '2026-11-04T09:42:00Z',
            source_timezone: 'UTC', status: 'Active', availability: 'Busy'
          }
        }]
      }});
    }
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {'source-label': 'literal'});
  await fire(environment.document.getElementById('source-form'), 'submit');
  const bytes = new TextEncoder().encode('BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n');
  const input = environment.document.getElementById('ics-file');
  input.files = [{size: bytes.length, arrayBuffer: async () => bytes.buffer}];
  await fire(input, 'change');
  await environment.document.getElementById('ics-preview').click();
  const rendered = environment.document.getElementById('ics-preview-table').textContent;
  assert.match(rendered, /<script>globalThis\.compromised = true<\/script>/);
  assert.match(rendered, /<img src="https:\/\/invalid\.example\/private-canary"/);
  assert.equal(environment.document.querySelectorAll('script').length, 0);
  assert.equal(environment.document.querySelectorAll('img').length, 0);
  assert.equal(globalThis.compromised, undefined);
  assert.equal(calls.length, 2);
  assert.equal(calls.filter(call => call.url.startsWith('https://')).length, 0);
});
