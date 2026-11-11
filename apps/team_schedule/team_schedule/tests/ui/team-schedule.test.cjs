'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
  ApiError,
  ExpectedError,
  createClient,
  resolveRange,
  createSchedulePayload,
  collectResolutions,
  intervalsOverlap,
  splitUtcWindow,
  mergeUtcIntervals,
  parseUsers,
  formatUtc,
  zonedLocalInput,
  resetMemoryState,
  bytesToBase64,
  readIcsFile
} = require('../../public/team-schedule.js');

function response(body, ok = true, status = 200) {
  return {ok, status, json: async () => body};
}

test('client uses same-origin POST, CSRF and exact method URL', async () => {
  const calls = [];
  const client = createClient({
    csrfToken: 'test-token',
    fetchImpl: async (url, options) => {
      calls.push({url, options});
      return response({message: {schedule: {name: 'opaque'}}});
    }
  });
  const result = await client.post('get', {name: 'opaque'});
  assert.equal(result.schedule.name, 'opaque');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/method/team_schedule.api.get');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.credentials, 'same-origin');
  assert.equal(calls[0].options.headers['X-Frappe-CSRF-Token'], 'test-token');
  assert.equal(calls[0].options.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(calls[0].options.body), {name: 'opaque'});
});

test('client exposes only safe error code and DST offset candidates', async () => {
  const client = createClient({
    csrfToken: 'token',
    fetchImpl: async () => response({message: {error: {code: 'AMBIGUOUS_LOCAL_TIME', offset_minutes: [-300, -240]}}}, false, 400)
  });
  await assert.rejects(client.post('resolve_local', {local: '2026-11-01T01:30', timezone: 'America/New_York'}), error => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.code, 'AMBIGUOUS_LOCAL_TIME');
    assert.deepEqual(error.offsetMinutes, [-300, -240]);
    assert.equal(Object.hasOwn(error, 'privateText'), false);
    return true;
  });
});

test('range resolution retries an ambiguous start with explicit offset', async () => {
  const payloads = [];
  const client = {
    post: async (method, payload) => {
      assert.equal(method, 'resolve_local');
      payloads.push(payload);
      if (payloads.length === 1) throw new ApiError('AMBIGUOUS_LOCAL_TIME', 400, {offset_minutes: [-300, -240]});
      return {utc: payload.local + ':00Z', timezone: payload.timezone, offset_minutes: payload.offset_minutes ?? 0};
    }
  };
  const options = {
    startLocal: '2026-11-01T01:30', endLocal: '2026-11-01T02:07', timezone: 'America/New_York', startOffset: null, endOffset: -300
  };
  await assert.rejects(resolveRange(client, options), error => error.field === 'start');
  const range = await resolveRange(client, {...options, startOffset: -240});
  assert.deepEqual(payloads[1], {local: options.startLocal, timezone: options.timezone, offset_minutes: -240});
  assert.deepEqual(payloads[2], {local: options.endLocal, timezone: options.timezone, offset_minutes: -300});
  assert.equal(range.start_offset_minutes, -240);
  assert.equal(range.end_offset_minutes, -300);
});

test('create DTO preserves arbitrary minute boundaries and member ACL', () => {
  const values = {title: '分钟日程', description: '<b>纯文本</b>', timezone: 'Asia/Shanghai', availability: 'Busy'};
  const range = {start_utc: '2026-11-04T01:07:00Z', end_utc: '2026-11-04T01:42:00Z'};
  const payload = createSchedulePayload(values, range, [{user: 'member@example.test', access: 'Read'}], '0f19e1b0-2c56-46b0-a2f1-c7f4857b6c42');
  assert.deepEqual(payload, {
    title: '分钟日程', description: '<b>纯文本</b>',
    start_utc: '2026-11-04T01:07:00Z', end_utc: '2026-11-04T01:42:00Z',
    source_timezone: 'Asia/Shanghai', availability: 'Busy',
    members: [{user: 'member@example.test', access: 'Read'}],
    request_id: '0f19e1b0-2c56-46b0-a2f1-c7f4857b6c42'
  });
});

test('ICS selection emits only exact per-item replacement resolutions', () => {
  const items = [
    {index: 0, action: 'create', allowed_resolutions: [], expected_revision: null},
    {index: 1, action: 'local_conflict', allowed_resolutions: ['replace_from_source'], expected_revision: 7},
    {index: 2, action: 'local_conflict', allowed_resolutions: ['replace_from_source'], expected_revision: 9}
  ];
  assert.deepEqual(collectResolutions(items, new Set([1])), [{index: 1, action: 'replace_from_source', expected_revision: 7}]);
  assert.deepEqual(collectResolutions(items, new Set()), []);
  assert.throws(() => collectResolutions(items, new Set([0])), ExpectedError);
  assert.throws(() => collectResolutions([{...items[1], expected_revision: null}], new Set([1])), ExpectedError);
});

test('half-open overlap accepts adjacent intervals', () => {
  assert.equal(intervalsOverlap('2026-11-04T09:07:00Z', '2026-11-04T09:42:00Z', '2026-11-04T09:42:00Z', '2026-11-04T10:05:00Z'), false);
  assert.equal(intervalsOverlap('2026-11-04T09:07:00Z', '2026-11-04T09:42:00Z', '2026-11-04T09:41:00Z', '2026-11-04T10:05:00Z'), true);
});

test('busy query users always include self and deduplicate', () => {
  assert.deepEqual(parseUsers('b@example.test, a@example.test b@example.test', 'a@example.test'), ['a@example.test', 'b@example.test']);
});

test('display and edit round-trip use explicit IANA zones', () => {
  const utc = '2026-11-04T17:37:00Z';
  assert.match(formatUtc(utc, 'Asia/Shanghai'), /GMT\+8/);
  assert.match(formatUtc(utc, 'Asia/Kolkata'), /GMT\+5:30/);
  assert.equal(zonedLocalInput(utc, 'Asia/Shanghai'), '2026-11-05T01:37');
  assert.equal(zonedLocalInput(utc, 'Asia/Kolkata'), '2026-11-04T23:07');
});

test('memory reset invalidates stale responses and removes business and ICS state', () => {
  const state = {
    epoch: 3, items: [{title: 'private'}], nextCursor: 'secret-cursor', listQuery: {startUtc: 'x'}, selected: {description: 'private'},
    icsGeneration: 4, ics: {sourceId: 'source', fileBase64: 'private', receipt: 'receipt', expiresIn: 900, items: [{preview: {title: 'private'}}]}
  };
  resetMemoryState(state);
  assert.equal(state.epoch, 4);
  assert.equal(state.icsGeneration, 5);
  assert.deepEqual(state.items, []);
  assert.equal(state.nextCursor, null);
  assert.equal(state.listQuery, null);
  assert.equal(state.selected, null);
  assert.deepEqual(state.ics, {sourceId: '', fileBase64: '', receipt: '', expiresIn: 0, items: []});
});

test('ICS reader enforces UTF-8 and 1MiB without altering content', async () => {
  const bytes = new TextEncoder().encode('\ufeffBEGIN:VCALENDAR\r\n');
  const file = {size: bytes.length, arrayBuffer: async () => bytes.buffer};
  assert.equal(await readIcsFile(file), bytesToBase64(bytes));
  const invalid = new Uint8Array([0xff]);
  await assert.rejects(readIcsFile({size: 1, arrayBuffer: async () => invalid.buffer}), ExpectedError);
  await assert.rejects(readIcsFile({size: 1048577, arrayBuffer: async () => new ArrayBuffer(0)}), ExpectedError);
});

test('busy precheck windows cover 8 and 31 days in contiguous segments of at most 7 days', () => {
  for (const [end, count] of [['2026-11-09T09:42:00Z', 2], ['2026-12-02T09:07:00Z', 5]]) {
    const start = '2026-11-01T09:07:00Z';
    const windows = splitUtcWindow(start, end);
    assert.equal(windows.length, count);
    assert.equal(windows[0].start_utc, start);
    assert.equal(windows.at(-1).end_utc, end);
    for (let index = 0; index < windows.length; index += 1) {
      assert.ok(Date.parse(windows[index].end_utc) - Date.parse(windows[index].start_utc) <= 7 * 86400000);
      if (index) assert.equal(windows[index].start_utc, windows[index - 1].end_utc);
    }
  }
});

test('busy intervals are merged across precheck segment boundaries', () => {
  assert.deepEqual(mergeUtcIntervals([
    {start_utc: '2026-11-08T00:00:00Z', end_utc: '2026-11-08T02:00:00Z'},
    {start_utc: '2026-11-07T23:00:00Z', end_utc: '2026-11-08T00:00:00Z'},
    {start_utc: '2026-11-09T00:00:00Z', end_utc: '2026-11-09T01:00:00Z'}
  ]), [
    {start_utc: '2026-11-07T23:00:00Z', end_utc: '2026-11-08T02:00:00Z'},
    {start_utc: '2026-11-09T00:00:00Z', end_utc: '2026-11-09T01:00:00Z'}
  ]);
});

test('Framework non-envelope rejections stay distinct from explicit application errors', async () => {
  for (const [status, body] of [[403, {exc_type: 'PermissionError', _server_messages: '[]'}], [417, {exc_type: 'ValidationError'}]]) {
    const client = createClient({csrfToken: 'token', fetchImpl: async () => response(body, false, status)});
    await assert.rejects(client.post('get', {name: 'private'}), error => {
      assert.equal(error.code, 'FRAMEWORK_REJECTED');
      assert.equal(error.status, status);
      assert.equal(error.business, false);
      return true;
    });
  }
  const invalidJson = createClient({csrfToken: 'token', fetchImpl: async () => ({ok: false, status: 403, json: async () => { throw new Error('not JSON'); }})});
  await assert.rejects(invalidJson.post('get', {name: 'private'}), error => error.code === 'FRAMEWORK_REJECTED' && error.status === 403 && !error.business);
  const application = createClient({csrfToken: 'token', fetchImpl: async () => response({message: {error: {code: 'INVALID_INPUT'}}}, false, 417)});
  await assert.rejects(application.post('resolve_local', {}), error => error.code === 'INVALID_INPUT' && error.status === 417 && error.business);
});

const {layoutTimeline, nextLocalDate} = require('../../public/team-schedule.js');

test('timeline preserves exact arbitrary minutes, clips cross-day intervals and excludes adjacent outside items', () => {
  const item = (name, start, end) => ({name, start_utc: start, end_utc: end});
  const result = layoutTimeline([
    item('short', '2026-11-01T09:07:00Z', '2026-11-01T09:08:00Z'),
    item('overnight', '2026-10-31T23:00:00Z', '2026-11-01T01:00:00Z'),
    item('continues', '2026-11-01T23:00:00Z', '2026-11-02T02:00:00Z'),
    item('outside', '2026-11-02T00:00:00Z', '2026-11-02T01:00:00Z')
  ], '2026-11-01T00:00:00Z', '2026-11-02T00:00:00Z');
  assert.equal(result.height, 1728);
  assert.equal(result.segments.length, 3);
  const short = result.segments.find(segment => segment.schedule.name === 'short');
  assert.equal(short.top, 547 * 1.2);
  assert.equal(short.height, 1.2);
  assert.equal(result.segments[0].continuesBefore, true);
  assert.equal(result.segments[2].continuesAfter, true);
});

test('overlap clusters use separate columns while end-equals-start reuses a column', () => {
  const values = [
    ['a', '09:00', '10:00'], ['b', '09:30', '10:30'], ['c', '10:00', '11:00'], ['d', '11:00', '12:00']
  ].map(([name, start, end]) => ({name, start_utc: '2026-11-01T' + start + ':00Z', end_utc: '2026-11-01T' + end + ':00Z'}));
  const {segments} = layoutTimeline(values, '2026-11-01T00:00:00Z', '2026-11-02T00:00:00Z');
  assert.deepEqual(segments.map(segment => segment.column), [0, 1, 0, 0]);
  assert.deepEqual(segments.map(segment => segment.columns), [2, 2, 2, 1]);
});

test('DST elapsed-day heights are 23/25 hours and local date navigation does not add UTC 24 hours', () => {
  assert.equal(layoutTimeline([], '2026-03-08T05:00:00Z', '2026-03-09T04:00:00Z').height, 23 * 72);
  assert.equal(layoutTimeline([], '2026-11-01T04:00:00Z', '2026-11-02T05:00:00Z').height, 25 * 72);
  assert.equal(nextLocalDate('2026-12-31'), '2027-01-01');
  assert.equal(nextLocalDate('2026-03-01', -1), '2026-02-28');
  assert.throws(() => nextLocalDate('2026-02-30'), ExpectedError);
});
