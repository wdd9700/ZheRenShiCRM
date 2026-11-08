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

test('stale list success cannot clear the newer session warning or restore business data', async () => {
  const calls = [];
  const listResponse = deferred();
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push({url, payload});
    if (url.endsWith('.resolve_local')) return jsonResponse({message: {utc: payload.local + ':00Z', timezone: payload.timezone, offset_minutes: 0}});
    if (url.endsWith('.list')) return listResponse.promise;
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {
    'list-start': '2026-11-01T09:00',
    'list-end': '2026-11-02T09:00',
    'list-timezone': 'UTC'
  });
  const pending = fire(environment.document.getElementById('list-form'), 'submit');
  for (let attempt = 0; attempt < 5 && methodCalls(calls, '.list').length === 0; attempt += 1) await flush();
  assert.equal(methodCalls(calls, '.list').length, 1);
  await fire(environment.document, 'visibilitychange');
  listResponse.resolve(jsonResponse({message: {items: [{name: 'stale-private-item'}], next_cursor: null}}));
  await pending;
  assert.equal(environment.document.getElementById('schedule-list').children.length, 0);
  assert.match(environment.document.getElementById('session-status').textContent, /请刷新页面/);
  assert.doesNotMatch(environment.document.getElementById('session-status').textContent, /后续显式请求已成功/);
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

test('successful explicit list after visibility changes the stale warning to a neutral state', async () => {
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    if (url.endsWith('.resolve_local')) return jsonResponse({message: {utc: payload.local + ':00Z', timezone: payload.timezone, offset_minutes: 0}});
    if (url.endsWith('.list')) return jsonResponse({message: {items: [], next_cursor: null}});
    throw new Error('unexpected request ' + url);
  });
  await fire(environment.document, 'visibilitychange');
  assert.match(environment.document.getElementById('session-status').textContent, /请刷新页面/);
  setValues(environment.document, {
    'list-start': '2026-11-01T09:00',
    'list-end': '2026-11-02T09:00',
    'list-timezone': 'UTC'
  });
  await fire(environment.document.getElementById('list-form'), 'submit');
  assert.match(environment.document.getElementById('session-status').textContent, /后续显式请求已成功/);
  assert.doesNotMatch(environment.document.getElementById('session-status').textContent, /请刷新页面/);
  assert.doesNotMatch(environment.document.getElementById('session-status').className, /error/);
  assert.match(environment.document.getElementById('list-status').textContent, /已加载0条/);
});

test('cancel success clears the previous edit result while preserving revision and neutral session state', async () => {
  const calls = [];
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push({url, payload});
    if (url.endsWith('.resolve_local')) return jsonResponse({message: {utc: payload.local + ':00Z', timezone: payload.timezone, offset_minutes: 0}});
    if (url.endsWith('availability.api.query')) return jsonResponse({message: {busy: [{user: 'owner@example.test', intervals: []}], common_free: [], display_timezone: 'UTC'}});
    if (url.endsWith('.create') || url.endsWith('.update') || url.endsWith('.cancel')) {
      const revision = url.endsWith('.create') ? 1 : url.endsWith('.update') ? 4 : 5;
      const source = url.endsWith('.update') ? payload.changes : payload;
      return jsonResponse({message: {schedule: {
        name: 'schedule-revision', owner: 'owner@example.test', title: source.title || 'revision title', description: source.description || '',
        start_utc: source.start_utc || '2026-11-04T09:07:00Z', end_utc: source.end_utc || '2026-11-04T09:42:00Z',
        source_timezone: source.source_timezone || 'UTC', status: url.endsWith('.cancel') ? 'Cancelled' : 'Active',
        availability: source.availability || 'Busy', revision, members: []
      }}});
    }
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {
    'schedule-title': 'revision title',
    'schedule-description': '',
    'schedule-start': '2026-11-04T09:07',
    'schedule-end': '2026-11-04T09:42',
    'schedule-timezone': 'UTC',
    'schedule-availability': 'Busy'
  });
  await fire(environment.document.getElementById('schedule-form'), 'submit');
  await environment.document.getElementById('edit-schedule').click();
  setValues(environment.document, {'schedule-title': 'updated title'});
  await fire(environment.document.getElementById('schedule-form'), 'submit');
  assert.match(environment.document.getElementById('schedule-status').textContent, /已更新日程，当前revision=4/);
  await environment.document.getElementById('cancel-schedule').click();
  assert.equal(environment.document.getElementById('schedule-status').textContent, '');
  assert.match(environment.document.getElementById('detail-status').textContent, /日程已取消，revision=5/);
  assert.equal(methodCalls(calls, '.cancel')[0].payload.expected_revision, 4);
  assert.match(environment.document.getElementById('session-status').textContent, /后续显式请求已成功/);
  assert.doesNotMatch(environment.document.getElementById('session-status').textContent, /请刷新页面/);
});

test('CRM changed message clears Cancelled detail and drafts and rejects late list data', async () => {
  const calls = [];
  const lateResponse = deferred();
  const cancelled = {
    name: 'cancelled-private', owner: 'owner@example.test', title: 'private cancelled title', description: 'private cancelled description',
    start_utc: '2026-11-04T09:07:00Z', end_utc: '2026-11-04T09:42:00Z', source_timezone: 'UTC',
    status: 'Cancelled', availability: 'Busy', revision: 5, members: []
  };
  let listCount = 0;
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    calls.push({url, payload});
    if (url.endsWith('.resolve_local')) return jsonResponse({message: {utc: payload.local + ':00Z', timezone: payload.timezone, offset_minutes: 0}});
    if (url.endsWith('.get')) return jsonResponse({message: {schedule: cancelled}});
    if (url.endsWith('.list')) {
      listCount += 1;
      if (listCount === 2) return lateResponse.promise;
      return jsonResponse({message: {items: [cancelled], next_cursor: 'next-page'}});
    }
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {
    'list-start': '2026-11-01T09:00',
    'list-end': '2026-11-08T09:00',
    'list-timezone': 'UTC'
  });
  await fire(environment.document.getElementById('list-form'), 'submit');
  await environment.document.getElementById('schedule-list').querySelectorAll('button')[0].click();
  assert.equal(environment.document.getElementById('detail-panel').hidden, false);
  assert.match(environment.document.getElementById('detail-content').textContent, /private cancelled title/);
  assert.match(environment.document.getElementById('detail-content').textContent, /Cancelled/);
  setValues(environment.document, {
    'editing-name': 'private-draft-id',
    'editing-revision': '5',
    'schedule-title': 'private draft title',
    'schedule-description': 'private draft description'
  });
  const sender = new environment.window.BroadcastChannel('crm-account-boundary-c011000');
  sender.postMessage('unrelated-message');
  assert.equal(environment.document.getElementById('detail-panel').hidden, false);
  await environment.document.getElementById('list-more').click();
  for (let attempt = 0; attempt < 5 && methodCalls(calls, '.list').length < 2; attempt += 1) await flush();
  assert.equal(methodCalls(calls, '.list').length, 2);
  sender.postMessage('changed');
  assert.equal(environment.document.getElementById('detail-panel').hidden, true);
  assert.equal(environment.document.getElementById('detail-content').textContent, '');
  assert.equal(environment.document.getElementById('editing-name').value, '');
  assert.equal(environment.document.getElementById('schedule-title').value, '');
  assert.equal(environment.document.getElementById('schedule-description').value, '');
  assert.match(environment.document.getElementById('session-status').textContent, /另一标签的账号会话发生变化/);
  lateResponse.resolve(jsonResponse({message: {items: [{...cancelled, name: 'late-private', title: 'late private title'}], next_cursor: null}}));
  await flush();
  assert.equal(environment.document.getElementById('schedule-list').children.length, 0);
  assert.doesNotMatch(environment.document.getElementById('schedule-list').textContent, /late private title/);
  assert.doesNotMatch(environment.document.getElementById('session-status').textContent, /后续显式请求已成功/);
});

test('init without BroadcastChannel keeps the existing visibility fallback', async () => {
  const environment = createDom(html, async () => { throw new Error('unexpected request'); });
  environment.window.BroadcastChannel = undefined;
  init(environment.document, environment.window);
  await fire(environment.document, 'visibilitychange');
  assert.match(environment.document.getElementById('session-status').textContent, /页面重新可见/);
});

function timelineItem(name, start, end, title = name) {
  return {name, owner: 'owner@example.test', title, description: '', start_utc: start, end_utc: end,
    source_timezone: 'UTC', availability: 'Busy', status: 'Active', revision: 1, members: []};
}

test('day view resolves both local midnights, renders true short blocks, continuation labels and paginated overlaps', async () => {
  const calls = [];
  const short = timelineItem('short', '2026-11-01T13:07:00Z', '2026-11-01T13:08:00Z', '<img src=x>');
  const crossing = timelineItem('cross', '2026-11-01T03:00:00Z', '2026-11-01T05:00:00Z');
  const environment = createDom(html, async (url, options) => {
    const payload = JSON.parse(options.body); calls.push({url, payload});
    if (url.endsWith('.resolve_local')) return jsonResponse({message: {utc: payload.local.startsWith('2026-11-01') ? '2026-11-01T04:00:00Z' : '2026-11-02T05:00:00Z', offset_minutes: 0}});
    if (url.endsWith('.list')) return jsonResponse({message: payload.cursor ? {items: [timelineItem('overlap', '2026-11-01T13:07:00Z', '2026-11-01T14:00:00Z')], next_cursor: null} : {items: [short, crossing], next_cursor: 'next'}});
    if (url.endsWith('.get')) return jsonResponse({message: {schedule: short}});
    throw new Error('unexpected request ' + url);
  });
  environment.window.PhilosopherCRMText = {enums: {Busy: '占用'}, timeline: {continuesBefore: '承接前日'}};
  init(environment.document, environment.window);
  setValues(environment.document, {'day-date': '2026-11-01', 'list-timezone': 'America/New_York'});
  await fire(environment.document.getElementById('day-form'), 'submit');
  assert.deepEqual(methodCalls(calls, '.resolve_local').map(call => call.payload.local), ['2026-11-01T00:00', '2026-11-02T00:00']);
  const container = environment.document.getElementById('schedule-list');
  assert.equal(container.querySelector('.timeline').style.height, '1800px');
  assert.match(container.textContent, /25小时/);
  assert.match(container.textContent, /承接前日/);
  assert.match(container.textContent, /占用/);
  assert.match(container.textContent, /<img src=x>/);
  assert.equal(container.querySelectorAll('img').length, 0);
  const thin = container.querySelectorAll('.timeline-block').find(button => button.title.includes('<img src=x>'));
  assert.equal(thin.style.height, '1.2px');
  assert.equal(thin.style.top, (547 * 1.2) + 'px');
  assert.match(environment.document.getElementById('list-status').textContent, /不是完整结果/);
  const ticks = container.querySelectorAll('.timeline-tick').map(tick => tick.textContent);
  assert.ok(ticks.some(value => value.includes('01:00') && value.includes('GMT-4')));
  assert.ok(ticks.some(value => value.includes('01:00') && value.includes('GMT-5')));
  assert.equal(container.querySelector('.timeline-scroll').scrollTop, 0);
  await thin.click();
  assert.equal(methodCalls(calls, '.get').length, 1);
  assert.match(environment.document.getElementById('list-status').textContent, /详情已按当前权限/);
  assert.match(container.querySelector('.timeline-incomplete').textContent, /不是完整结果/);
  await environment.document.getElementById('list-more').click();
  await flush();
  assert.equal(methodCalls(calls, '.list')[1].payload.cursor, 'next');
  assert.ok(container.querySelectorAll('.timeline-block').some(block => block.style.width === 'calc(50% - 4px)'));
  assert.match(environment.document.getElementById('list-status').textContent, /全部结果/);
  assert.equal(container.querySelector('.timeline-incomplete'), null);
  const sender = new environment.window.BroadcastChannel('crm-account-boundary-c011000');
  sender.postMessage('changed');
  assert.equal(container.children.length, 0);
  assert.equal(container.textContent, '');
});

test('newer day navigation wins over a late old response and 409 clears all timeline labels', async () => {
  const late = deferred(); let lists = 0;
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    if (url.endsWith('.resolve_local')) return jsonResponse({message: {utc: payload.local + ':00Z', offset_minutes: 0}});
    if (url.endsWith('.list')) {
      lists += 1;
      if (lists === 1) return late.promise;
      return jsonResponse({message: {items: [timelineItem('new', '2026-11-02T09:00:00Z', '2026-11-02T10:00:00Z')], next_cursor: null}});
    }
    if (url.endsWith('.get')) return jsonResponse({message: {error: {code: 'REVISION_CONFLICT'}}}, false, 409);
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {'day-date': '2026-11-01', 'list-timezone': 'UTC'});
  const old = fire(environment.document.getElementById('day-form'), 'submit');
  for (let i = 0; i < 5 && !lists; i += 1) await flush();
  await environment.document.getElementById('day-next').click();
  late.resolve(jsonResponse({message: {items: [timelineItem('old-private', '2026-11-01T09:00:00Z', '2026-11-01T10:00:00Z')], next_cursor: null}}));
  await old;
  const container = environment.document.getElementById('schedule-list');
  assert.match(container.textContent, /2026-11-02/);
  assert.doesNotMatch(container.textContent, /old-private/);
  await container.querySelectorAll('button')[0].click();
  assert.equal(container.children.length, 0);
  assert.match(environment.document.getElementById('list-status').textContent, /版本冲突/);
});

test('late detail from a previous day cannot reopen the detail panel after navigation', async () => {
  const detail = deferred(); let getStarted = false;
  const oldItem = timelineItem('old-detail', '2026-11-01T09:00:00Z', '2026-11-01T10:00:00Z');
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    if (url.endsWith('.resolve_local')) return jsonResponse({message: {utc: payload.local + ':00Z', offset_minutes: 0}});
    if (url.endsWith('.list')) return jsonResponse({message: {items: payload.start_utc.startsWith('2026-11-01') ? [oldItem] : [], next_cursor: null}});
    if (url.endsWith('.get')) { getStarted = true; return detail.promise; }
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {'day-date': '2026-11-01', 'list-timezone': 'UTC'});
  await fire(environment.document.getElementById('day-form'), 'submit');
  const pending = environment.document.getElementById('schedule-list').querySelectorAll('button')[0].click();
  await flush();
  assert.equal(getStarted, true);
  await environment.document.getElementById('day-next').click();
  detail.resolve(jsonResponse({message: {schedule: oldItem}}));
  await pending;
  assert.equal(environment.document.getElementById('detail-panel').hidden, true);
  assert.doesNotMatch(environment.document.getElementById('detail-content').textContent, /old-detail/);
});

test('midnight event keeps the initial scroll at zero and session clear removes persistent pagination notice', async () => {
  const environment = setup(async (url, options) => {
    const payload = JSON.parse(options.body);
    if (url.endsWith('.resolve_local')) return jsonResponse({message: {utc: payload.local + ':00Z', offset_minutes: 0}});
    if (url.endsWith('.list')) return jsonResponse({message: {items: [timelineItem('midnight', '2026-11-01T00:00:00Z', '2026-11-01T00:20:00Z')], next_cursor: 'more'}});
    throw new Error('unexpected request ' + url);
  });
  setValues(environment.document, {'day-date': '2026-11-01', 'list-timezone': 'UTC'});
  await fire(environment.document.getElementById('day-form'), 'submit');
  const container = environment.document.getElementById('schedule-list');
  assert.equal(container.querySelector('.timeline-block').style.top, '0px');
  assert.equal(container.querySelector('.timeline-scroll').scrollTop, 0);
  assert.match(container.querySelector('.timeline-incomplete').textContent, /不是完整结果/);
  await fire(environment.document, 'visibilitychange');
  assert.equal(container.children.length, 0);
  assert.equal(container.querySelector('.timeline-incomplete'), null);
});
