import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMIT = '36bd8859f2a6345a620477bc708d0546e8c3f08a'
DEFAULT_APP = HERE.parents[2] / 'apps/team_schedule/team_schedule'
SIDEBAR = 'frontend/src/components/Layouts/AppSidebar.vue'
ROUTER = 'frontend/src/router.js'
RESUME = 'frontend/src/resumeRuntime.js'
BOUNDARY = 'frontend/node_modules/frappe-ui/src/resources/accountBoundary.js'
WEBSITE = 'crm/www/crm.py'
PAGE = 'frontend/src/pages/TeamSchedule.vue'
CONTROLLER = 'frontend/src/pages/teamScheduleController.mjs'
CATALOG = 'frontend/src/pages/teamScheduleCatalog.mjs'
CSS = 'frontend/src/pages/teamSchedule.css'
HTML_SOURCE = 'www/team-schedule.html'
JS_SOURCE = 'public/team-schedule.js'
CSS_SOURCE = 'public/team-schedule.css'
CATALOG_SOURCE = 'public/crm-zh-cn.js'
TARGETS = {SIDEBAR, ROUTER, RESUME, BOUNDARY, WEBSITE, PAGE, CONTROLLER, CATALOG, CSS}
SOURCES = {HTML_SOURCE, JS_SOURCE, CSS_SOURCE, CATALOG_SOURCE}


def sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def once(text, anchor, revised):
    if text.count(anchor) != 1:
        raise ValueError(f'Missing or ambiguous source anchor: {anchor[:80]!r}')
    return text.replace(anchor, revised, 1)


def payload(name):
    return (HERE / 'payload' / name).read_bytes().decode('utf-8')


def scope_css(text):
    def scope_rule(match):
        indent, selectors = match.groups()
        scoped = []
        for selector in selectors.split(','):
            selector = selector.strip()
            if selector.startswith('.crm-standalone '):
                selector = selector.removeprefix('.crm-standalone ')
            scoped.append('.crm-native-schedule ' + selector)
        return indent + ', '.join(scoped) + ' {'

    return re.sub(r'^([ \t]*)(\.[^\n{]+?) \{', scope_rule, text, flags=re.M)


def transform(target, current, source):
    text = current.decode('utf-8') if current is not None else None
    if target == SIDEBAR:
        text = once(text, '            href="/team-schedule"\n',
                    '            :route="{ name: \'TeamSchedule\' }"\n'
                    '            :active="route.name === \'TeamSchedule\'"\n')
        text = once(text, '  return route.query.view || route.name',
                    "  return route.name === 'TeamSchedule' ? route.name : route.query.view || route.name")
    elif target == ROUTER:
        anchor = "  {\n    path: '/dashboard',"
        text = once(text, anchor, "  {\n    path: '/team-schedule',\n    name: 'TeamSchedule',\n"
                    "    component: () => import('@/pages/TeamSchedule.vue'),\n  },\n" + anchor)
        text = once(text, "window.location.href = '/login?redirect-to=/crm'",
                    "window.location.href = to.name === 'TeamSchedule'\n"
                    "      ? '/login?redirect-to=%2Fcrm%2Fteam-schedule'\n"
                    "      : '/login?redirect-to=/crm'")
    elif target == RESUME:
        text = once(text, '      try { snapshot = captureResume(router.currentRoute.value); supported = true }',
                    '''      const route = router.currentRoute.value
      try {
        if (route.name === 'TeamSchedule') {
          // Do not bypass the existing safe-resume restriction for global editors.
          if (document.querySelector('[role="dialog"], [contenteditable="true"]')) throw Error('Unsupported editor')
          snapshot = { name: route.name, fullPath: route.fullPath }
        } else snapshot = captureResume(route)
        supported = true
      }''')
        text = once(text, "      const doctype = ['Leads'",
                    '''      if (snapshot.name === 'TeamSchedule') {
        const path = snapshot.fullPath
        context.phase?.('HYDRATE')
        accountBoundary.hydrate()
        context.phase?.('BOOT')
        await boot()
        context.phase?.('ROUTER')
        await router.isReady()
        await nextTick()
        let revision
        do {
          revision = accountBoundary.readRevision
          await nextTick()
          await context.settleReads()
          await nextTick()
        } while (revision !== accountBoundary.readRevision)
        context.assertCurrent()
        context.phase?.('ROUTE_CHECK')
        if (router.currentRoute.value.name === 'Not Permitted') {
          throw Object.assign(Error('Current read access denied'), { status: 403 })
        }
        if (router.currentRoute.value.name !== 'TeamSchedule' || router.currentRoute.value.fullPath !== path) {
          throw Error('Route changed during recovery')
        }
        return {
          commit() {},
          afterCommit() { window.dispatchEvent(new Event('crm-team-schedule-active')) },
        }
      }
      const doctype = ['Leads\'''')
    elif target == BOUNDARY:
        text = once(text, "        login.href = '/login?redirect-to=/crm'",
                    "        const loginTarget = /^\\/crm\\/team-schedule\\/?$/.test(location.pathname)\n"
                    "          ? '/login?redirect-to=%2Fcrm%2Fteam-schedule' : '/login?redirect-to=/crm'\n"
                    "        login.href = loginTarget")
        text = once(text, "            location.assign('/login?redirect-to=/crm')", '            location.assign(loginTarget)')
    elif target == WEBSITE:
        anchor = '\tif not check_app_permission():'
        text = once(text, anchor,
                    '\tif frappe.session.user == "Guest" and frappe.request.path in ("/crm/team-schedule", "/crm/team-schedule/"):\n'
                    '\t\tfrappe.local.flags.redirect_location = "/login?redirect-to=%2Fcrm%2Fteam-schedule"\n'
                    '\t\tredirect = frappe.Redirect()\n'
                    '\t\tredirect.http_status_code = 302\n'
                    '\t\traise redirect\n\n' + anchor)
    elif target == PAGE:
        html = source[HTML_SOURCE].decode('utf-8')
        start = '  <section class="timeline-section"'
        end = '</main>'
        if html.count(start) != 1 or html.count(end) != 1:
            raise ValueError('Unexpected legacy schedule section bounds')
        sections = start + html.split(start, 1)[1].split(end, 1)[0]
        text = once(payload('TeamSchedule.vue'), '    <!-- schedule-sections -->\n',
                    ''.join('  ' + line if line.strip() else line for line in sections.splitlines(keepends=True)))
    elif target == CONTROLLER:
        js = source[JS_SOURCE].decode('utf-8')
        marker = '  const exported = {'
        if not js.startswith('(() => {\n') or js.count(marker) != 1:
            raise ValueError('Unexpected legacy controller wrapper')
        text = js.removeprefix('(() => {\n').split(marker, 1)[0] + 'export { init };\n'
    elif target == CATALOG:
        js = source[CATALOG_SOURCE].decode('utf-8')
        js = once(js, '(() => {\n', '')
        js = once(js, '  window.PhilosopherCRMText = ', 'export default ')
        text = once(js, '})();', '').rstrip() + '\n'
    elif target == CSS:
        text = payload('native-controls.css') + '\n' + scope_css(source[CSS_SOURCE].decode('utf-8'))
    else:
        raise ValueError('Unexpected S020 target: ' + target)
    return text.encode('utf-8')


def checked_path(root, name):
    path = root / name
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Linked path refused: ' + name)
    if not path.parent.resolve(strict=True).is_relative_to(root):
        raise ValueError('Path escapes root: ' + name)
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('Expected an ordinary file: ' + name)
    return path


def apply(root, app_source, mode='apply'):
    root = root.resolve(strict=True)
    if subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() != COMMIT:
        raise ValueError('CRM HEAD mismatch')
    manifest = json.loads((HERE / 'manifest.json').read_bytes())
    entries = manifest['targets']
    if (manifest['crm_commit'] != COMMIT or len(entries) != len(TARGETS) or
            {entry['target'] for entry in entries} != TARGETS or set(manifest['app_sources']) != SOURCES):
        raise ValueError('S020 manifest whitelist mismatch')
    source_root = app_source.resolve(strict=True)
    sources = {}
    for name, expected in manifest['app_sources'].items():
        # App inputs are Git text and may be checked out with CRLF on Windows.
        sources[name] = checked_path(source_root, name).read_bytes().replace(b'\r\n', b'\n')
        if sha(sources[name]) != expected:
            raise ValueError('S020 app source SHA mismatch: ' + name)
    pending = []
    phase = 'after' if mode == 'verify' else 'before'
    for entry in entries:
        name = entry['target']
        path = checked_path(root, name)
        current = path.read_bytes() if path.exists() else None
        if sha(current) != entry[phase]:
            raise ValueError(f'S020 {phase} mismatch: {name} ({sha(current)})')
        if mode != 'verify':
            updated = transform(name, current, sources)
            if sha(updated) != entry['after']:
                raise ValueError('S020 result SHA mismatch: ' + name)
            pending.append((path, updated))
    if mode == 'apply':
        staged = []
        try:
            for path, updated in pending:
                temporary = path.with_name(path.name + '.s020-tmp')
                with temporary.open('xb') as stream:
                    staged.append((temporary, path))
                    stream.write(updated)
            for temporary, path in staged:
                os.replace(temporary, path)
        finally:
            for temporary, _ in staged:
                temporary.unlink(missing_ok=True)
    return len(entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', type=Path)
    parser.add_argument('--app-source', type=Path, default=DEFAULT_APP)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    mode = 'check' if args.check else 'verify' if args.verify else 'apply'
    try:
        count = apply(args.crm_root, args.app_source, mode)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('S020 REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)
    print(f'PASS S020 {mode}: {count} exact CRM targets')
