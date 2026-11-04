(() => {
  'use strict';

  const API_PREFIX = '/api/method/';
  const ERROR_TEXT = {
    AUTH_REQUIRED: '登录已失效，请重新登录。',
    FORBIDDEN: '当前身份或权限已变化，旧数据已清除。',
    NOT_FOUND: '记录不存在或当前身份无权访问，旧数据已清除。',
    INVALID_INPUT: '输入不符合要求；请检查分钟、时区、DST与字段内容。',
    REVISION_CONFLICT: '版本冲突：他人已先修改。旧详情和编辑已清除，请重新加载后再决定。',
    IDEMPOTENCY_CONFLICT: '创建请求标识已用于不同内容，请清空表单后重试。',
    LIMIT_EXCEEDED: '数据或扫描量超过限制，未返回不完整结果。',
    RATE_LIMITED: '忙闲查询过于频繁，请稍后重试。',
    UNSUPPORTED_ICS: 'ICS包含不支持的格式或属性，未应用导入。',
    INVALID_TIME: 'ICS包含无效或不支持的日期时间。',
    INVALID_UID: 'ICS包含无效UID。',
    UNSUPPORTED_TEXT: '内容无法原样保存，未导入该项。',
    WRITE_FAILED: '服务端未能写入该项，请重新预览后重试。',
    DEPENDENCY_UNAVAILABLE: 'ICS解析依赖当前不可用，未预览或导入。',
    INTERNAL_ERROR: '服务端暂不可用，未显示旧业务数据。',
    INVALID_RESPONSE: '服务端未返回有效结果，未显示旧业务数据。',
    NETWORK_ERROR: '网络请求失败，结果未知；旧业务显示已清除，请重新核验。'
  };

  class ApiError extends Error {
    constructor(code, status = 0, details = {}) {
      super(code);
      this.name = 'ApiError';
      this.code = code;
      this.status = status;
      this.offsetMinutes = details.offset_minutes;
      this.field = null;
    }
  }

  class ExpectedError extends Error {}

  function safeErrorText(error) {
    return ERROR_TEXT[error && error.code] || ERROR_TEXT.INVALID_RESPONSE;
  }

  function formatIcsCode(code) {
    return code && ERROR_TEXT[code] ? code + '；' + ERROR_TEXT[code] : code;
  }

  function createClient({fetchImpl, csrfToken}) {
    async function post(method, payload, namespace = 'team_schedule.api') {
      let response;
      try {
        response = await fetchImpl(API_PREFIX + namespace + '.' + method, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-Frappe-CSRF-Token': csrfToken
          },
          body: JSON.stringify(payload)
        });
      } catch {
        throw new ApiError('NETWORK_ERROR');
      }
      let body = null;
      try {
        body = await response.json();
      } catch {
        throw new ApiError(response.status === 401 ? 'AUTH_REQUIRED' : 'INVALID_RESPONSE', response.status);
      }
      const message = body && body.message;
      if (!response.ok) {
        const code = message && message.error && message.error.code;
        const details = message && message.error && typeof message.error === 'object' ? message.error : {};
        throw new ApiError(code || (response.status === 401 ? 'AUTH_REQUIRED' : 'INVALID_RESPONSE'), response.status, details);
      }
      if (!message || typeof message !== 'object') {
        throw new ApiError('INVALID_RESPONSE', response.status);
      }
      return message;
    }
    return {post};
  }

  async function resolveLocal(client, local, timezone, offsetMinutes = null) {
    const payload = {local, timezone};
    if (offsetMinutes !== null) payload.offset_minutes = offsetMinutes;
    return client.post('resolve_local', payload);
  }

  async function resolveRange(client, options) {
    let start;
    try {
      start = await resolveLocal(client, options.startLocal, options.timezone, options.startOffset);
    } catch (error) {
      error.field = 'start';
      throw error;
    }
    let end;
    try {
      end = await resolveLocal(client, options.endLocal, options.timezone, options.endOffset);
    } catch (error) {
      error.field = 'end';
      throw error;
    }
    return {
      start_utc: start.utc,
      end_utc: end.utc,
      start_offset_minutes: start.offset_minutes,
      end_offset_minutes: end.offset_minutes
    };
  }

  function createSchedulePayload(values, range, members, requestId) {
    return {
      title: values.title,
      description: values.description,
      start_utc: range.start_utc,
      end_utc: range.end_utc,
      source_timezone: values.timezone,
      availability: values.availability,
      members,
      request_id: requestId
    };
  }

  function collectResolutions(items, selectedIndexes) {
    const selected = selectedIndexes instanceof Set ? selectedIndexes : new Set(selectedIndexes);
    const resolutions = [];
    for (const item of items) {
      if (!selected.has(item.index)) continue;
      const allowed = Array.isArray(item.allowed_resolutions) ? item.allowed_resolutions : [];
      if (item.action !== 'local_conflict' || !allowed.includes('replace_from_source') || !Number.isInteger(item.expected_revision) || item.expected_revision < 1) {
        throw new ExpectedError('所选项目不允许覆盖，请重新预览。');
      }
      resolutions.push({
        index: item.index,
        action: 'replace_from_source',
        expected_revision: item.expected_revision
      });
    }
    return resolutions;
  }

  function intervalsOverlap(startA, endA, startB, endB) {
    return startA < endB && endA > startB;
  }

  function parseUsers(value, currentUser) {
    const others = String(value || '').split(/[\s,]+/).map(item => item.trim()).filter(Boolean);
    return [...new Set([currentUser, ...others])];
  }

  function formatOffset(offsetMinutes) {
    const sign = offsetMinutes < 0 ? '-' : '+';
    const absolute = Math.abs(offsetMinutes);
    return 'UTC' + sign + String(Math.floor(absolute / 60)).padStart(2, '0') + ':' + String(absolute % 60).padStart(2, '0');
  }

  function formatUtc(utc, timezone) {
    const formatted = new Intl.DateTimeFormat('zh-CN', {
      timeZone: timezone,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
      timeZoneName: 'shortOffset'
    }).format(new Date(utc));
    return formatted + '；' + timezone;
  }

  function zonedLocalInput(utc, timezone) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone,
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).formatToParts(new Date(utc));
    const values = {};
    for (const part of parts) values[part.type] = part.value;
    return values.year + '-' + values.month + '-' + values.day + 'T' + values.hour + ':' + values.minute;
  }

  function resetMemoryState(state) {
    state.epoch += 1;
    state.items = [];
    state.nextCursor = null;
    state.listQuery = null;
    state.selected = null;
    state.icsGeneration += 1;
    state.ics = {sourceId: '', fileBase64: '', receipt: '', expiresIn: 0, items: []};
    return state;
  }

  function bytesToBase64(bytes) {
    let binary = '';
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return btoa(binary);
  }

  async function readIcsFile(file) {
    if (!file) throw new ExpectedError('请选择ICS文件。');
    if (file.size > 1048576) throw new ExpectedError('ICS文件超过1MiB。');
    const bytes = new Uint8Array(await file.arrayBuffer());
    try {
      new TextDecoder('utf-8', {fatal: true}).decode(bytes);
    } catch {
      throw new ExpectedError('ICS不是有效UTF-8文件。');
    }
    return bytesToBase64(bytes);
  }

  function init(document, window) {
    const $ = id => document.getElementById(id);
    const currentUser = document.body.dataset.currentUser;
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    const client = createClient({fetchImpl: window.fetch.bind(window), csrfToken});
    const state = {
      epoch: 0,
      items: [],
      nextCursor: null,
      listQuery: null,
      selected: null,
      createRequestId: window.crypto.randomUUID(),
      icsGeneration: 0,
      ics: {sourceId: '', fileBase64: '', receipt: '', expiresIn: 0, items: []}
    };

    $('current-user').textContent = currentUser;

    function message(id, text, isError = false) {
      const element = $(id);
      element.textContent = text;
      element.classList.toggle('error', isError);
    }

    function makeButton(text, handler, className = '') {
      const element = document.createElement('button');
      element.type = 'button';
      element.textContent = text;
      if (className) element.className = className;
      element.addEventListener('click', handler);
      return element;
    }

    function makeTable(container, headers) {
      const table = document.createElement('table');
      const head = document.createElement('thead');
      const row = document.createElement('tr');
      for (const header of headers) {
        const cell = document.createElement('th');
        cell.scope = 'col';
        cell.textContent = header;
        row.append(cell);
      }
      head.append(row);
      table.append(head);
      const body = document.createElement('tbody');
      table.append(body);
      container.replaceChildren(table);
      return body;
    }

    function cell(row, text) {
      const element = document.createElement('td');
      element.textContent = text === null || text === undefined || text === '' ? '—' : String(text);
      row.append(element);
      return element;
    }

    function populateTimezones() {
      const fallback = ['UTC', 'Asia/Shanghai', 'Asia/Kolkata', 'America/New_York'];
      const supported = typeof window.Intl.supportedValuesOf === 'function' ? window.Intl.supportedValuesOf('timeZone') : [];
      const zones = [...new Set([...fallback, ...supported])].sort((a, b) => a === 'UTC' ? -1 : b === 'UTC' ? 1 : a.localeCompare(b));
      for (const select of document.querySelectorAll('select.timezone-select')) {
        for (const zone of zones) {
          const option = document.createElement('option');
          option.value = zone;
          option.textContent = zone;
          select.append(option);
        }
        select.value = 'UTC';
      }
    }

    function clearOffset(prefix, field) {
      const select = $(prefix + '-' + field + '-offset');
      select.replaceChildren();
      $(prefix + '-' + field + '-offset-row').hidden = true;
    }

    function showOffsetChoices(prefix, field, offsets) {
      const select = $(prefix + '-' + field + '-offset');
      select.replaceChildren();
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = '请选择';
      select.append(empty);
      for (const offset of offsets || []) {
        const option = document.createElement('option');
        option.value = String(offset);
        option.textContent = formatOffset(offset) + '（' + offset + '分钟）';
        select.append(option);
      }
      $(prefix + '-' + field + '-offset-row').hidden = false;
    }

    function selectedOffset(prefix, field) {
      const value = $(prefix + '-' + field + '-offset').value;
      return value === '' ? null : Number(value);
    }

    async function resolveFormRange(prefix) {
      try {
        return await resolveRange(client, {
          startLocal: $(prefix + '-start').value,
          endLocal: $(prefix + '-end').value,
          timezone: $(prefix + '-timezone').value,
          startOffset: selectedOffset(prefix, 'start'),
          endOffset: selectedOffset(prefix, 'end')
        });
      } catch (error) {
        if (error.code === 'AMBIGUOUS_LOCAL_TIME' && error.field) {
          showOffsetChoices(prefix, error.field, error.offsetMinutes);
          throw new ExpectedError('该当地时间有双重DST解释，请选择' + (error.field === 'start' ? '开始' : '结束') + '时间的offset后重新提交。');
        }
        throw error;
      }
    }

    function resetEditor() {
      $('schedule-form').reset();
      $('editing-name').value = '';
      $('editing-revision').value = '';
      $('schedule-timezone').value = 'UTC';
      $('create-members').hidden = false;
      $('create-member-rows').replaceChildren();
      $('schedule-submit').textContent = '创建日程';
      state.createRequestId = window.crypto.randomUUID();
      clearOffset('schedule', 'start');
      clearOffset('schedule', 'end');
    }

    function clearBusiness({clearDrafts = false} = {}) {
      resetMemoryState(state);
      $('schedule-submit').disabled = false;
      $('schedule-list').replaceChildren();
      $('list-more').hidden = true;
      $('detail-panel').hidden = true;
      $('detail-content').replaceChildren();
      $('busy-results').replaceChildren();
      $('ics-preview-panel').hidden = true;
      $('ics-preview-table').replaceChildren();
      $('ics-result-table').replaceChildren();
      $('ics-confirm').checked = false;
      $('ics-apply').disabled = true;
      $('ics-preview').disabled = true;
      $('ics-file').value = '';
      if (clearDrafts) {
        resetEditor();
        $('source-label').value = '';
        $('viewer-user').value = '';
        $('busy-users').value = '';
      }
    }

    function identityFailure(error) {
      return ['AUTH_REQUIRED', 'FORBIDDEN', 'NOT_FOUND', 'REVISION_CONFLICT'].includes(error.code);
    }

    function fail(error, statusId) {
      const clearDrafts = identityFailure(error);
      clearBusiness({clearDrafts});
      message(statusId, safeErrorText(error), true);
      message('session-status', clearDrafts ? '身份、权限或版本边界已变化；内存业务数据和草稿已清除。' : '请求失败；已清除旧业务显示，请重新加载并核验。', true);
    }

    function addMemberRow(container, member = null) {
      const row = document.createElement('div');
      row.className = 'member-row';
      const userLabel = document.createElement('label');
      userLabel.textContent = '用户ID';
      const user = document.createElement('input');
      user.required = true;
      user.value = member ? member.user : '';
      user.className = 'member-user';
      userLabel.append(user);
      const accessLabel = document.createElement('label');
      accessLabel.textContent = '权限';
      const access = document.createElement('select');
      access.className = 'member-access';
      for (const value of ['Read', 'Edit']) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        access.append(option);
      }
      access.value = member ? member.access : 'Read';
      accessLabel.append(access);
      row.append(userLabel, accessLabel, makeButton('移除', () => row.remove()));
      container.append(row);
    }

    function collectMembers(container) {
      const result = [];
      const seen = new Set([currentUser]);
      for (const row of container.querySelectorAll('.member-row')) {
        const user = row.querySelector('.member-user').value.trim();
        const access = row.querySelector('.member-access').value;
        if (!user) throw new ExpectedError('成员用户ID不能为空。');
        if (seen.has(user)) throw new ExpectedError('成员不能重复，也不能把owner加入子表。');
        seen.add(user);
        result.push({user, access});
      }
      return result;
    }

    function canEdit(schedule) {
      if (schedule.owner === currentUser) return true;
      const self = (schedule.members || []).find(member => member.user === currentUser);
      return Boolean(self && self.access === 'Edit');
    }

    function renderSchedules() {
      if (!state.items.length) {
        $('schedule-list').textContent = '当前窗口没有返回日程。';
        $('list-more').hidden = true;
        return;
      }
      const timezone = state.listQuery ? state.listQuery.timezone : 'UTC';
      const body = makeTable($('schedule-list'), ['开始', '结束', '标题', 'owner', '占用', '状态', 'revision', '操作']);
      for (const schedule of state.items) {
        const row = document.createElement('tr');
        if (schedule.status === 'Cancelled') row.className = 'cancelled';
        cell(row, formatUtc(schedule.start_utc, timezone));
        cell(row, formatUtc(schedule.end_utc, timezone));
        cell(row, schedule.title);
        cell(row, schedule.owner);
        cell(row, schedule.availability);
        cell(row, schedule.status);
        cell(row, schedule.revision);
        const actions = cell(row, '');
        actions.replaceChildren(makeButton('查看详情', () => viewSchedule(schedule.name)));
        body.append(row);
      }
      $('list-more').hidden = !state.nextCursor;
    }

    function renderDetails() {
      const schedule = state.selected;
      if (!schedule) {
        $('detail-panel').hidden = true;
        return;
      }
      $('detail-panel').hidden = false;
      const body = makeTable($('detail-content'), ['字段', '值']);
      const timezone = state.listQuery ? state.listQuery.timezone : schedule.source_timezone;
      const values = [
        ['标题', schedule.title],
        ['说明', schedule.description],
        ['开始', formatUtc(schedule.start_utc, timezone)],
        ['结束', formatUtc(schedule.end_utc, timezone)],
        ['UTC开始／结束', schedule.start_utc + ' 至 ' + schedule.end_utc],
        ['源时区', schedule.source_timezone],
        ['owner', schedule.owner],
        ['占用／状态', schedule.availability + '／' + schedule.status],
        ['revision', schedule.revision],
        ['成员', (schedule.members || []).map(member => member.user + '（' + member.access + '，' + (member.occupies ? '已接受占用' : '未接受占用') + '）').join('\n') || '无']
      ];
      for (const [label, value] of values) {
        const row = document.createElement('tr');
        cell(row, label);
        cell(row, value).className = 'detail-text';
        body.append(row);
      }
      const owner = schedule.owner === currentUser;
      const self = (schedule.members || []).find(member => member.user === currentUser);
      $('member-panel').hidden = !owner || schedule.status !== 'Active';
      $('participation-panel').hidden = !self || schedule.status !== 'Active';
      if (self) $('occupies').checked = Boolean(self.occupies);
      $('edit-schedule').hidden = !canEdit(schedule) || schedule.status !== 'Active';
      $('cancel-schedule').hidden = !canEdit(schedule) || schedule.status !== 'Active';
      if (owner) {
        $('member-rows').replaceChildren();
        for (const member of schedule.members || []) addMemberRow($('member-rows'), member);
      }
    }

    function acceptMutation(schedule) {
      state.selected = schedule;
      const index = state.items.findIndex(item => item.name === schedule.name);
      if (index >= 0) state.items[index] = schedule;
      renderSchedules();
      renderDetails();
    }

    async function fetchList(query, append = false) {
      const epoch = state.epoch;
      if (!append) {
        state.items = [];
        state.selected = null;
        state.listQuery = query;
        renderSchedules();
        renderDetails();
      }
      message('list-status', '正在重新核验权限并加载…');
      try {
        const result = await client.post('list', {
          start_utc: query.startUtc,
          end_utc: query.endUtc,
          include_cancelled: query.includeCancelled,
          cursor: append ? state.nextCursor : null,
          limit: 100
        });
        if (epoch !== state.epoch) return;
        state.items = append ? state.items.concat(result.items || []) : (result.items || []);
        state.nextCursor = result.next_cursor || null;
        state.listQuery = query;
        renderSchedules();
        message('list-status', '已加载' + state.items.length + '条；时间均含显示时区与UTC offset。');
      } catch (error) {
        if (epoch === state.epoch) fail(error, 'list-status');
      }
    }

    async function viewSchedule(name) {
      const epoch = state.epoch;
      state.selected = null;
      renderDetails();
      message('list-status', '正在读取当前详情…');
      try {
        const result = await client.post('get', {name});
        if (epoch !== state.epoch) return;
        state.selected = result.schedule;
        renderDetails();
        message('list-status', '详情已按当前权限重新读取。');
      } catch (error) {
        if (epoch === state.epoch) fail(error, 'list-status');
      }
    }

    async function confirmOwnOverlap(range, timezone) {
      const result = await client.post('query', {
        users: [currentUser],
        start_utc: range.start_utc,
        end_utc: range.end_utc,
        min_minutes: 1,
        display_timezone: timezone
      }, 'team_schedule.availability.api');
      const own = (result.busy || []).find(item => item.user === currentUser);
      const overlaps = (own ? own.intervals : []).filter(interval => intervalsOverlap(range.start_utc, range.end_utc, interval.start_utc, interval.end_utc));
      if (!overlaps.length) return true;
      const text = overlaps.map(interval => formatUtc(interval.start_utc, timezone) + ' 至 ' + formatUtc(interval.end_utc, timezone)).join('\n');
      return window.confirm('本次时间与以下本人Busy区间交叠：\n' + text + '\n这只是查询快照，不会锁定时间。仍要保存吗？');
    }

    async function saveSchedule(event) {
      event.preventDefault();
      const epoch = state.epoch;
      $('schedule-submit').disabled = true;
      message('schedule-status', '正在解析当地时间…');
      try {
        const range = await resolveFormRange('schedule');
        const editingName = $('editing-name').value;
        const values = {
          title: $('schedule-title').value,
          description: $('schedule-description').value,
          timezone: $('schedule-timezone').value,
          availability: $('schedule-availability').value
        };
        if (!values.title.trim()) throw new ExpectedError('标题不能为空。');
        if (range.start_utc >= range.end_utc) throw new ExpectedError('结束必须晚于开始。');
        const members = editingName ? [] : collectMembers($('create-member-rows'));
        message('schedule-status', '正在检查本人忙闲交叠…');
        const confirmed = await confirmOwnOverlap(range, values.timezone);
        if (epoch !== state.epoch) return;
        if (!confirmed) {
          message('schedule-status', '未保存；可修改时间后重试。');
          return;
        }
        let result;
        if (editingName) {
          result = await client.post('update', {
            name: editingName,
            expected_revision: Number($('editing-revision').value),
            changes: {
              title: values.title,
              description: values.description,
              start_utc: range.start_utc,
              end_utc: range.end_utc,
              source_timezone: values.timezone,
              availability: values.availability
            }
          });
        } else {
          result = await client.post('create', createSchedulePayload(values, range, members, state.createRequestId));
        }
        if (epoch !== state.epoch) return;
        const saved = result.schedule;
        resetEditor();
        state.selected = saved;
        renderDetails();
        message('schedule-status', (editingName ? '已更新' : '已创建') + '日程，当前revision=' + saved.revision + '。');
        if (state.listQuery) await fetchList(state.listQuery);
      } catch (error) {
        if (epoch !== state.epoch) return;
        if (error instanceof ExpectedError) message('schedule-status', error.message, true);
        else fail(error, 'schedule-status');
      } finally {
        if (epoch === state.epoch) $('schedule-submit').disabled = false;
      }
    }

    function editSelected() {
      const schedule = state.selected;
      if (!schedule) return;
      $('editing-name').value = schedule.name;
      $('editing-revision').value = String(schedule.revision);
      $('schedule-title').value = schedule.title;
      $('schedule-description').value = schedule.description || '';
      $('schedule-timezone').value = schedule.source_timezone;
      $('schedule-start').value = zonedLocalInput(schedule.start_utc, schedule.source_timezone);
      $('schedule-end').value = zonedLocalInput(schedule.end_utc, schedule.source_timezone);
      $('schedule-availability').value = schedule.availability;
      $('create-members').hidden = true;
      $('schedule-submit').textContent = '保存日程修改';
      clearOffset('schedule', 'start');
      clearOffset('schedule', 'end');
      message('schedule-status', '正在编辑revision=' + schedule.revision + '；保存将携带该版本。');
      $('schedule-form').scrollIntoView({behavior: 'smooth', block: 'start'});
    }

    async function cancelSelected() {
      const schedule = state.selected;
      if (!schedule) return;
      if (!window.confirm('确认取消该日程？此操作不删除记录，也不会取消他人的其他安排。')) return;
      const epoch = state.epoch;
      try {
        const result = await client.post('cancel', {name: schedule.name, expected_revision: schedule.revision});
        if (epoch !== state.epoch) return;
        acceptMutation(result.schedule);
        message('detail-status', '日程已取消，revision=' + result.schedule.revision + '。');
      } catch (error) {
        if (epoch === state.epoch) fail(error, 'detail-status');
      }
    }

    async function saveMembers() {
      const schedule = state.selected;
      if (!schedule) return;
      const epoch = state.epoch;
      try {
        const members = collectMembers($('member-rows'));
        const result = await client.post('set_members', {name: schedule.name, expected_revision: schedule.revision, members});
        if (epoch !== state.epoch) return;
        acceptMutation(result.schedule);
        message('detail-status', '成员权限已保存，revision=' + result.schedule.revision + '。');
      } catch (error) {
        if (epoch !== state.epoch) return;
        if (error instanceof ExpectedError) message('detail-status', error.message, true);
        else fail(error, 'detail-status');
      }
    }

    async function saveParticipation() {
      const schedule = state.selected;
      if (!schedule) return;
      const epoch = state.epoch;
      try {
        const result = await client.post('set_participation', {
          name: schedule.name,
          expected_revision: schedule.revision,
          occupies: $('occupies').checked
        });
        if (epoch !== state.epoch) return;
        acceptMutation(result.schedule);
        message('detail-status', '本人占用状态已保存，revision=' + result.schedule.revision + '。');
      } catch (error) {
        if (epoch === state.epoch) fail(error, 'detail-status');
      }
    }

    async function saveGrant(event) {
      event.preventDefault();
      const epoch = state.epoch;
      try {
        const result = await client.post('set_busy_grant', {viewer_user: $('viewer-user').value.trim(), allow: $('grant-allow').checked});
        if (epoch !== state.epoch) return;
        message('grant-status', '已' + (result.allow ? '授予' : '撤回') + '对该用户的本人忙闲授权。');
      } catch (error) {
        if (epoch === state.epoch) fail(error, 'grant-status');
      }
    }

    async function queryAvailability(event) {
      event.preventDefault();
      const epoch = state.epoch;
      $('busy-results').replaceChildren();
      try {
        const range = await resolveFormRange('busy');
        const users = parseUsers($('busy-users').value, currentUser);
        const timezone = $('busy-timezone').value;
        const result = await client.post('query', {
          users,
          start_utc: range.start_utc,
          end_utc: range.end_utc,
          min_minutes: Number($('min-minutes').value),
          display_timezone: timezone
        }, 'team_schedule.availability.api');
        if (epoch !== state.epoch) return;
        const body = makeTable($('busy-results'), ['类型／用户', '脱敏时间段（开始至结束）']);
        for (const item of result.busy || []) {
          const row = document.createElement('tr');
          cell(row, 'Busy：' + item.user);
          cell(row, (item.intervals || []).map(interval => formatUtc(interval.start_utc, timezone) + ' 至 ' + formatUtc(interval.end_utc, timezone)).join('\n') || '窗口内无占用').className = 'detail-text';
          body.append(row);
        }
        const row = document.createElement('tr');
        cell(row, '共同空闲');
        cell(row, (result.common_free || []).map(interval => formatUtc(interval.start_utc, timezone) + ' 至 ' + formatUtc(interval.end_utc, timezone)).join('\n') || '无满足最小时长的共同空闲').className = 'detail-text';
        body.append(row);
        message('busy-status', '查询完成；结果不含日程ID、标题、正文或成员详情。');
      } catch (error) {
        if (epoch !== state.epoch) return;
        if (error instanceof ExpectedError) message('busy-status', error.message, true);
        else fail(error, 'busy-status');
      }
    }

    async function createSource(event) {
      event.preventDefault();
      const epoch = state.epoch;
      try {
        const result = await client.post('create_source', {label: $('source-label').value.trim()}, 'team_schedule.ics.api');
        if (epoch !== state.epoch) return;
        state.ics.sourceId = result.source_id;
        state.ics.receipt = '';
        state.ics.items = [];
        $('ics-preview-panel').hidden = true;
        $('ics-preview').disabled = !state.ics.fileBase64;
        message('source-status', '来源已创建，ID：' + result.source_id + '。请选择文件并预览。');
      } catch (error) {
        if (epoch === state.epoch) fail(error, 'source-status');
      }
    }

    async function fileChanged() {
      const generation = ++state.icsGeneration;
      state.ics.fileBase64 = '';
      state.ics.receipt = '';
      state.ics.items = [];
      $('ics-preview-panel').hidden = true;
      $('ics-result-table').replaceChildren();
      $('ics-preview').disabled = true;
      try {
        const base64 = await readIcsFile($('ics-file').files[0]);
        if (generation !== state.icsGeneration) return;
        state.ics.fileBase64 = base64;
        $('ics-preview').disabled = !state.ics.sourceId;
        message('ics-status', '文件已在内存读取；请选择预览，尚未写入。');
      } catch (error) {
        if (generation !== state.icsGeneration) return;
        message('ics-status', error instanceof ExpectedError ? error.message : safeErrorText(error), true);
      }
    }

    function updateIcsApply() {
      $('ics-apply').disabled = !state.ics.receipt || !$('ics-confirm').checked;
    }

    function renderIcsPreview() {
      const body = makeTable($('ics-preview-table'), ['index', 'action／code', '源标题', '源说明', '源时间', '状态／占用', '目标revision', '逐项覆盖']);
      for (const item of state.ics.items) {
        const row = document.createElement('tr');
        cell(row, item.index);
        cell(row, String(item.action || '') + (item.code ? '／' + formatIcsCode(item.code) : ''));
        const preview = item.preview || {};
        cell(row, preview.title);
        cell(row, preview.description).className = 'detail-text';
        cell(row, preview.start_utc && preview.end_utc ? formatUtc(preview.start_utc, preview.source_timezone || 'UTC') + ' 至 ' + formatUtc(preview.end_utc, preview.source_timezone || 'UTC') : '—');
        cell(row, String(preview.status || '—') + '／' + String(preview.availability || '—'));
        cell(row, item.expected_revision);
        const choice = cell(row, '');
        const allowed = item.action === 'local_conflict' && (item.allowed_resolutions || []).includes('replace_from_source');
        if (allowed) {
          const label = document.createElement('label');
          const checkbox = document.createElement('input');
          checkbox.type = 'checkbox';
          checkbox.className = 'ics-resolution';
          checkbox.dataset.index = String(item.index);
          label.append(checkbox, document.createTextNode(' 以源版本覆盖'));
          choice.append(label);
        }
        body.append(row);
      }
      $('ics-preview-panel').hidden = false;
      $('ics-confirm').checked = false;
      updateIcsApply();
    }

    async function previewIcs() {
      const epoch = state.epoch;
      if (!state.ics.sourceId || !state.ics.fileBase64) {
        message('ics-status', '请先创建来源并选择ICS文件。', true);
        return;
      }
      try {
        const result = await client.post('preview', {source_id: state.ics.sourceId, file_base64: state.ics.fileBase64}, 'team_schedule.ics.api');
        if (epoch !== state.epoch) return;
        state.ics.receipt = result.receipt;
        state.ics.expiresIn = result.expires_in;
        state.ics.items = result.items || [];
        renderIcsPreview();
        message('ics-status', '预览完成，receipt有效' + result.expires_in + '秒。逐项检查后再独立确认应用。');
      } catch (error) {
        if (epoch === state.epoch) fail(error, 'ics-status');
      }
    }

    async function applyIcs() {
      const epoch = state.epoch;
      if (!state.ics.receipt || !$('ics-confirm').checked) return;
      try {
        const selected = new Set([...document.querySelectorAll('input.ics-resolution:checked')].map(input => Number(input.dataset.index)));
        const resolutions = collectResolutions(state.ics.items, selected);
        const result = await client.post('apply', {
          receipt: state.ics.receipt,
          source_id: state.ics.sourceId,
          file_base64: state.ics.fileBase64,
          confirm: true,
          resolutions
        }, 'team_schedule.ics.api');
        if (epoch !== state.epoch) return;
        const body = makeTable($('ics-result-table'), ['index', 'result', 'code', 'schedule', 'revision']);
        for (const item of result.items || []) {
          const row = document.createElement('tr');
          cell(row, item.index);
          cell(row, item.result);
          cell(row, formatIcsCode(item.code));
          cell(row, item.schedule_name);
          cell(row, item.revision);
          body.append(row);
        }
        state.ics.receipt = '';
        $('ics-confirm').checked = false;
        updateIcsApply();
        message('ics-status', '服务端已返回逐项结果；未选覆盖的冲突项不会被写入。请重新预览以再次应用。');
        if (state.listQuery) await fetchList(state.listQuery);
      } catch (error) {
        if (epoch !== state.epoch) return;
        if (error instanceof ExpectedError) message('ics-status', error.message, true);
        else fail(error, 'ics-status');
      }
    }

    function sessionInvalidated(reason) {
      clearBusiness({clearDrafts: true});
      message('session-status', reason + ' 已清除全部内存业务显示和草稿，请刷新页面重新核验会话。', true);
    }

    populateTimezones();
    resetEditor();
    $('reload-page').addEventListener('click', () => window.location.reload());
    $('schedule-form').addEventListener('submit', saveSchedule);
    $('schedule-reset').addEventListener('click', () => { resetEditor(); message('schedule-status', '编辑已清空。'); });
    $('schedule-form').addEventListener('input', event => {
      if (!$('editing-name').value) state.createRequestId = window.crypto.randomUUID();
      if (['schedule-start', 'schedule-end', 'schedule-timezone'].includes(event.target.id)) {
        clearOffset('schedule', 'start');
        clearOffset('schedule', 'end');
      }
    });
    for (const prefix of ['list', 'busy']) {
      for (const field of ['start', 'end', 'timezone']) {
        $(prefix + '-' + field).addEventListener('input', () => { clearOffset(prefix, 'start'); clearOffset(prefix, 'end'); });
      }
    }
    $('add-create-member').addEventListener('click', () => addMemberRow($('create-member-rows')));
    $('add-member').addEventListener('click', () => addMemberRow($('member-rows')));
    $('list-form').addEventListener('submit', async event => {
      event.preventDefault();
      const epoch = state.epoch;
      try {
        const range = await resolveFormRange('list');
        if (range.start_utc >= range.end_utc) throw new ExpectedError('窗口结束必须晚于开始。');
        await fetchList({
          startUtc: range.start_utc,
          endUtc: range.end_utc,
          includeCancelled: $('include-cancelled').checked,
          timezone: $('list-timezone').value
        });
      } catch (error) {
        if (epoch !== state.epoch) return;
        if (error instanceof ExpectedError) message('list-status', error.message, true);
        else fail(error, 'list-status');
      }
    });
    $('list-more').addEventListener('click', () => { if (state.listQuery) fetchList(state.listQuery, true); });
    $('edit-schedule').addEventListener('click', editSelected);
    $('cancel-schedule').addEventListener('click', cancelSelected);
    $('save-members').addEventListener('click', saveMembers);
    $('save-participation').addEventListener('click', saveParticipation);
    $('grant-form').addEventListener('submit', saveGrant);
    $('availability-form').addEventListener('submit', queryAvailability);
    $('source-form').addEventListener('submit', createSource);
    $('ics-file').addEventListener('change', fileChanged);
    $('ics-preview').addEventListener('click', previewIcs);
    $('ics-confirm').addEventListener('change', updateIcsApply);
    $('ics-apply').addEventListener('click', applyIcs);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) sessionInvalidated('页面重新可见，会话可能已变化。'); });
    window.addEventListener('pageshow', event => { if (event.persisted) sessionInvalidated('浏览器恢复了历史页面。'); });
    window.addEventListener('storage', () => sessionInvalidated('同源浏览器存储发生变化。'));
  }

  const exported = {
    ApiError,
    ExpectedError,
    createClient,
    resolveLocal,
    resolveRange,
    createSchedulePayload,
    collectResolutions,
    intervalsOverlap,
    parseUsers,
    formatOffset,
    formatUtc,
    zonedLocalInput,
    resetMemoryState,
    bytesToBase64,
    readIcsFile,
    init
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = exported;
  if (typeof window !== 'undefined' && typeof document !== 'undefined') {
    window.TeamSchedule = exported;
    window.addEventListener('DOMContentLoaded', () => init(document, window), {once: true});
  }
})();
