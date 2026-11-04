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
