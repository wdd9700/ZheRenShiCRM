(() => {
  if (window.teamActivityAccessLoaded) return
  window.teamActivityAccessLoaded = true
  const message = '正式共享沟通：Comment 将向父记录读者发布。私人内容请使用 Private Note；Private 仍允许明确协作者及任务受派人读写。Note/Task及私域历史/附件无实时刷新或查看者名单，保存或撤权后请手动刷新；原生历史缓存计数可能不可用。'
  function annotate() {
    for (const editor of document.querySelectorAll('[contenteditable="true"], textarea')) {
      if (editor.closest('#team-activities') || editor.dataset.teamAccessNotice) continue
      editor.dataset.teamAccessNotice = '1'
      const notice = document.createElement('p')
      notice.className = 'team-access-notice'
      notice.style.cssText = 'font-size:13px;color:#713f12;background:#fef3c7;padding:8px;white-space:normal'
      notice.textContent = message + ' '
      const link = document.createElement('a')
      link.href = '/team-activities'
      link.textContent = '管理活动共享/撤回'
      link.style.textDecoration = 'underline'
      notice.append(link)
      editor.parentNode.insertBefore(notice, editor)
    }
    if (!document.getElementById('team-access-link')) {
      const link = document.createElement('a')
      link.id = 'team-access-link'
      link.href = '/team-activities'
      link.textContent = '活动私域/共享管理'
      link.style.cssText = 'position:fixed;bottom:8px;right:8px;z-index:9999;background:#fff;border:1px solid #64748b;border-radius:4px;padding:6px;font-size:13px'
      document.body.append(link)
    }
  }
  annotate()
  new MutationObserver(annotate).observe(document.body, { childList: true, subtree: true })
  if (window.frappe?.ui?.form) {
    for (const doctype of ['FCRM Note', 'CRM Task', 'Comment']) {
      frappe.ui.form.on(doctype, { refresh(frm) {
        frm.dashboard.set_headline_alert(message)
        frm.add_custom_button('活动私域/共享管理', () => { window.location.href = '/team-activities' })
      } })
    }
  }
})()
