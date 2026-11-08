(() => {
  const noticeStyle = document.createElement('p').style
  noticeStyle.cssText = 'font-size:14px;line-height:20px;color:var(--crm-text,#E8EAED);background:var(--crm-surface,#202329);border:1px solid var(--crm-border,#3A414B);border-left:3px solid var(--crm-gold,#E1BC70);border-radius:8px;padding:8px 12px;white-space:normal'
  const linkStyle = document.createElement('a').style
  linkStyle.cssText = 'position:fixed;bottom:8px;right:8px;z-index:9999;display:inline-flex;align-items:center;min-height:40px;color:var(--crm-text,#E8EAED);background:var(--crm-raised,#292D34);border:1px solid var(--crm-control-border,#697380);border-radius:8px;padding:8px 12px;font-size:14px;line-height:20px;text-decoration:underline;text-underline-offset:3px'
  function updateOwnedStyles() {
    for (const notice of document.querySelectorAll('.team-access-notice')) {
      if (notice.style.cssText !== noticeStyle.cssText) notice.style.cssText = noticeStyle.cssText
      for (const link of notice.querySelectorAll('a')) {
        if (link.getAttribute('href') !== '/team-activities') continue
        if (link.style.textDecoration !== 'underline') link.style.textDecoration = 'underline'
        if (link.style.color !== 'inherit') link.style.color = 'inherit'
      }
    }
    const link = document.getElementById('team-access-link')
    if (link?.getAttribute('href') === '/team-activities' && link.style.cssText !== linkStyle.cssText) link.style.cssText = linkStyle.cssText
  }
  updateOwnedStyles()
  if (window.teamActivityAccessLoaded) return
  window.teamActivityAccessLoaded = true
  const message = '正式共享沟通：Comment 将向父记录读者发布。私人内容请使用 Private Note；Private 仍允许明确协作者及任务受派人读写。Note/Task及私域历史/附件无实时刷新或查看者名单，保存或撤权后请手动刷新；原生历史缓存计数可能不可用。'
  function annotate() {
    for (const editor of document.querySelectorAll('[contenteditable="true"], textarea')) {
      if (editor.closest('#team-activities') || editor.dataset.teamAccessNotice) continue
      editor.dataset.teamAccessNotice = '1'
      const notice = document.createElement('p')
      notice.className = 'team-access-notice'
      notice.textContent = message + ' '
      const link = document.createElement('a')
      link.href = '/team-activities'
      link.textContent = '管理活动共享/撤回'
      notice.append(link)
      editor.parentNode.insertBefore(notice, editor)
    }
    if (!document.getElementById('team-access-link')) {
      const link = document.createElement('a')
      link.id = 'team-access-link'
      link.href = '/team-activities'
      link.textContent = '活动私域/共享管理'
      document.body.append(link)
    }
    updateOwnedStyles()
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
