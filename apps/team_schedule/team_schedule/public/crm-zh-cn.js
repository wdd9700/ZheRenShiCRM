(() => {
  'use strict';

  const enums = Object.freeze({
    Busy: '占用', Free: '空闲', Active: '进行中', Cancelled: '已取消',
    Read: '只读', Edit: '可编辑', Private: '私密', Shared: '共享'
  });
  const timeline = Object.freeze({
    continuesBefore: '承接前日', continuesAfter: '延续次日',
    empty: '所选日期没有日程', shortEvents: '短日程（按真实时长定位，完整标签见下方）',
    view: '查看详情'
  });
  const icsActions = Object.freeze({
    create: '新建', update: '更新', cancel: '取消', unknown_cancelled: '记录未知取消',
    duplicate: '重复，无需操作', stale: '来源版本过旧', version_conflict: '来源版本冲突',
    cancelled_source: '来源已取消', revision_conflict: '目标版本冲突',
    local_conflict: '本地修改冲突', error: '错误', replace_from_source: '以来源覆盖'
  });
  const errors = Object.freeze({
    AUTH_REQUIRED: '登录已失效，请重新登录。',
    FORBIDDEN: '当前身份或权限已变化，旧数据已清除。',
    NOT_FOUND: '记录不存在或当前身份无权访问，旧数据已清除。',
    INVALID_INPUT: '输入不符合要求；请检查分钟、时区、夏令时与字段内容。',
    AMBIGUOUS_LOCAL_TIME: '该当地时间有两个夏令时解释，请选择UTC偏移后重试。',
    REVISION_CONFLICT: '版本冲突：他人已先修改。旧详情和编辑已清除，请重新加载后再决定。',
    IDEMPOTENCY_CONFLICT: '创建请求标识已用于不同内容，请清空表单后重试。',
    LIMIT_EXCEEDED: '数据或扫描量超过限制，未返回不完整结果。',
    RATE_LIMITED: '忙闲查询过于频繁，请稍后重试。',
    UNSUPPORTED_ICS: 'ICS包含不支持的格式或属性，未应用导入。',
    INVALID_TIME: 'ICS包含无效或不支持的日期时间。',
    INVALID_UID: 'ICS包含无效UID。',
    DUPLICATE_UID: 'ICS文件中包含重复的UID。',
    UNSUPPORTED_TEXT: '内容无法原样保存，未导入该项。',
    WRITE_FAILED: '服务端未能写入该项，请重新预览后重试。',
    DEPENDENCY_UNAVAILABLE: 'ICS解析依赖当前不可用，未预览或导入。',
    INTERNAL_ERROR: '服务端暂不可用，未显示旧业务数据。',
    INVALID_RESPONSE: '服务端未返回有效结果，未显示旧业务数据。',
    FRAMEWORK_REJECTED: '系统拒绝了请求；敏感编辑已清除，请重新核验会话、权限与输入。',
    NETWORK_ERROR: '网络请求失败，结果未知；旧业务显示已清除，请重新核验。',
    STALE: '来源版本过旧，未写入。',
    VERSION_CONFLICT: '来源版本冲突，未写入。',
    CANCELLED_SOURCE: '来源项目已取消，未写入。',
    LOCAL_CONFLICT: '本地内容已修改，请重新预览并逐项决定。'
  });
  const dates = Object.freeze({
    timezone: '时区', sourceTimezone: '源时区', displayTimezone: '显示时区',
    utcOffset: 'UTC偏移', daylightSaving: '夏令时', start: '开始', end: '结束',
    select: '请选择', minutes: '分钟', noBusy: '窗口内无占用',
    noCommonFree: '无满足最小时长的共同空闲'
  });

  window.PhilosopherCRMText = Object.freeze({enums, timeline, icsActions, errors, dates});
})();
