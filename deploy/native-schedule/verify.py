import argparse
from html.parser import HTMLParser
import importlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

from contract import (APP, BASE_CONFIG, BASE_CONTROLLER_SHA, BASE_HTML_SHA, BASE_INDEX, CONTROLLER,
                      CRM_HEAD, FALLBACK_REVISION, FALLBACK_SHA, HTML, RECEIPT, SCHEMA,
                      patch_contract, safe_relative, sha)

BENCH = Path('/home/frappe/frappe-bench')
CONTEXT = Path('/home/frappe/native-schedule')
PREVIOUS = Path('/home/frappe/final-navigation')
PUBLIC = 'apps/crm/crm/public'
GENERATED_HTML = 'apps/crm/crm/www/crm.html'
STATE = CONTEXT / 'native-before.json'
STATIC_PREFIX = '/assets/crm/frontend/'


class Entrypoint(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.urls = set()
        self.modules = set()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'link'):
            url = attrs.get('src' if tag == 'script' else 'href', '')
            if url and url.startswith('/assets/crm/'):
                self.urls.add(url)
                if tag == 'script' and attrs.get('type') == 'module':
                    self.modules.add(url)


# Includes Vite dependency-map entries (assets/...) and direct ES module imports (./...).
CHUNK_REF = re.compile(r'''["'`]((?:\./|assets/|/assets/crm/frontend/)[A-Za-z0-9_./-]+\.(?:js|css))["'`]''')


def chunk_graph(root, entry):
    visited, pending = {}, [entry]
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        data = (root / safe_relative(name)).read_text(encoding='utf-8')
        visited[name] = data
        if not name.endswith('.js'):
            continue
        for match in CHUNK_REF.findall(data):
            if match.startswith('./'):
                reference = (Path(name).parent / match[2:]).as_posix()
            else:
                reference = match.removeprefix(STATIC_PREFIX)
            pending.append(safe_relative(reference))
    return visited


def verify_bundle(html_path, assets, previous_module):
    html = html_path.read_text(encoding='utf-8')
    parser = Entrypoint(html)
    if len(parser.modules) != 1 or previous_module in parser.modules or '哲人石CRM' not in html or 'boot.philosopher_language' not in html:
        raise RuntimeError('New, branded, localized CRM HTML module entry required')
    for url in parser.urls:
        if not (assets / safe_relative(url.removeprefix('/assets/'))).is_file():
            raise RuntimeError('Missing CRM HTML dependency: ' + url)
    entry = next(iter(parser.modules))
    if not entry.startswith(STATIC_PREFIX):
        raise RuntimeError('CRM module entry is not a local compiled asset')
    graph = chunk_graph(assets / 'crm/frontend', entry.removeprefix(STATIC_PREFIX))
    pages = [name for name in graph if re.fullmatch(r'assets/TeamSchedule-[\w-]+\.js', name)]
    styles = [name for name in graph if re.fullmatch(r'assets/TeamSchedule-[\w-]+\.css', name)]
    scripts = [data for name, data in graph.items() if name.endswith('.js')]
    if len(pages) != 1 or len(styles) != 1 or not graph[styles[0]].strip():
        raise RuntimeError('New CRM entry does not link the native schedule JS and CSS chunks')
    route = re.compile(
        r'''\{\s*path\s*:\s*(["'`])/team-schedule\1\s*,\s*name\s*:\s*(["'`])TeamSchedule\2'''
        r'''\s*,\s*component\s*:\s*[^{};]{0,160}?\bimport\(\s*(["'`])(?:\./|/assets/crm/frontend/assets/)'''
        + re.escape(Path(pages[0]).name) + r'''\3\s*\)'''
    )
    if not any(route.search(script) for script in scripts):
        raise RuntimeError('Compiled Vue route does not import the schedule page')
    page = graph[pages[0]]
    if '团队日程' not in page or not any('team_schedule.availability.api' in script for script in scripts):
        raise RuntimeError('Compiled native schedule page/controller markers are missing')
    if any(token in script for script in scripts for token in ('D020102', 'readFailureCode')):
        raise RuntimeError('Temporary read diagnostics in reachable CRM bundle')
    pwa = json.loads((assets / 'crm/frontend/manifest.webmanifest').read_bytes())
    if pwa.get('name') != '哲人石CRM' or pwa.get('short_name') != '哲人石CRM':
        raise RuntimeError('Built PWA branding drifted')
    return {key: sha(data.encode()) for key, data in graph.items()}, entry, pages[0], styles[0]


def checked_context():
    manifest = json.loads((CONTEXT / RECEIPT).read_bytes())
    if (manifest['schema'], manifest['base_index'], manifest['base_config'], manifest['fallback_revision']) != (SCHEMA, BASE_INDEX, BASE_CONFIG, FALLBACK_REVISION):
        raise RuntimeError('Invalid S021 receipt baseline')
    for name, expected in manifest['files'].items():
        path = CONTEXT / safe_relative(name)
        if not path.is_file() or path.is_symlink() or sha(path.read_bytes()) != expected:
            raise RuntimeError('Changed S021 context source: ' + name)
    return manifest, patch_contract(CONTEXT, manifest['files'])


def check_legacy_before():
    for name, expected in ((HTML, BASE_HTML_SHA), (CONTROLLER, BASE_CONTROLLER_SHA)):
        if sha((BENCH / APP / name).read_bytes()) != expected:
            raise RuntimeError('Published legacy predecessor differs: ' + name)


def install_legacy():
    check_legacy_before()
    for name in (CONTROLLER, HTML):
        (BENCH / APP / name).write_bytes((CONTEXT / 'legacy/target' / name).read_bytes())


def verify_legacy(manifest):
    for name in (CONTROLLER, HTML):
        if sha((BENCH / APP / name).read_bytes()) != manifest['files']['legacy/target/' + name]:
            raise RuntimeError('Packaged legacy asset differs: ' + name)
    if sha((BENCH / APP / HTML).read_bytes()) != FALLBACK_SHA:
        raise RuntimeError('Legacy fallback no longer preserves the reviewed return link')
    verify_legacy_controller(BENCH / APP / CONTROLLER)


def verify_legacy_controller(path):
    class Redirect(Exception):
        pass

    frappe = SimpleNamespace(session=SimpleNamespace(user='Guest'), conf={},
                             local=SimpleNamespace(flags=SimpleNamespace()), Redirect=Redirect,
                             sessions=SimpleNamespace(get_csrf_token=lambda: 'test-token'))
    with patch.dict(sys.modules, {'frappe': frappe}):
        module = runpy.run_path(str(path))
        for setting, user, location in (
            (None, 'Guest', '/login?redirect-to=%2Fteam-schedule'),
            (True, 'Guest', '/login?redirect-to=%2Fcrm%2Fteam-schedule'),
            (1, 'sales@example.invalid', '/crm/team-schedule'),
            (False, 'sales@example.invalid', None),
            ('1', 'sales@example.invalid', None),
            (None, 'sales@example.invalid', None),
        ):
            frappe.conf = {} if setting is None else {'team_schedule_native_workspace': setting}
            frappe.session.user = user
            frappe.local.flags = SimpleNamespace()
            context = SimpleNamespace()
            try:
                result = module['get_context'](context)
            except Redirect as error:
                if location is None or frappe.local.flags.redirect_location != location or error.http_status_code != 302:
                    raise RuntimeError('Unexpected packaged legacy redirect') from error
            else:
                if location is not None or result is not context or not context.no_cache or context.session_user != user or context.csrf_token != 'test-token':
                    raise RuntimeError('Unexpected packaged legacy fallback authorization/context')


def previous_expectations():
    sys.path.insert(0, str(PREVIOUS / 'deploy'))
    previous = importlib.import_module('verify_final_navigation')
    manifest = previous.source_manifest()
    state = json.loads(previous.STATE.read_bytes())
    sources = {**state['sources'], **{'apps/crm/' + p: h for p, h in previous.FILTER_AFTER.items()},
               **{'apps/crm/' + p: h for p, h in previous.CLEAN_SOURCES.items()}}
    endpoint = manifest['sort_endpoint']
    sources[endpoint['target']] = endpoint['after']
    return sources, state


def before():
    check_legacy_before()
    parser = Entrypoint((BENCH / GENERATED_HTML).read_text(encoding='utf-8'))
    if len(parser.modules) != 1:
        raise RuntimeError('Expected one original e14b6 CRM module entry')
    with STATE.open('x', encoding='utf-8') as out:
        json.dump(dict(module=next(iter(parser.modules))), out)


def assets(manifest, targets):
    if subprocess.check_output(['git', '-C', str(BENCH / 'apps/crm'), 'rev-parse', 'HEAD'], text=True).strip() != CRM_HEAD:
        raise RuntimeError('CRM checkout base differs')
    verify_legacy(manifest)
    sources, original = previous_expectations()
    sources.update({'apps/crm/' + p: entry['after'] for p, entry in targets.items()})
    sources.update({APP + p: manifest['files']['legacy/target/' + p] for p in (HTML, CONTROLLER)})
    for name, expected in sources.items():
        if sha((BENCH / name).read_bytes()) != expected:
            raise RuntimeError('Inherited or native source mismatch: ' + name)
    maps = [json.loads((BENCH / directory / 'assets.json').read_bytes()) for directory in ('assets', 'sites/assets')]
    if maps[0] != maps[1] or any(maps[0].get(key) != val for key, val in original['asset_manifest'].items()):
        raise RuntimeError('Predecessor Framework asset mappings changed')
    old_module = json.loads(STATE.read_bytes())['module']
    bundles = []
    for directory in ('assets', 'sites/assets'):
        root = BENCH / directory
        if (root / 'crm').resolve(strict=True) != (BENCH / PUBLIC).resolve(strict=True):
            raise RuntimeError('CRM runtime assets no longer resolve to shipped app public directory')
        for url in maps[0].values():
            if not url.startswith('/assets/') or not (root / safe_relative(url.removeprefix('/assets/'))).is_file():
                raise RuntimeError('Prior mapped asset missing: ' + url)
        for name, expected in original['assets'].items():
            if sha((root / safe_relative(name)).read_bytes()) != expected:
                raise RuntimeError('Prior protected static asset changed: ' + name)
        bundles.append(verify_bundle(BENCH / GENERATED_HTML, root, old_module))
    if bundles[0] != bundles[1]:
        raise RuntimeError('CRM built and runtime asset graph differ')
    graph, entry, page, css = bundles[0]
    proof = dict(entry=entry, page=page, css=css, assets=graph,
                 source_receipt=sha((CONTEXT / RECEIPT).read_bytes()), compatibility_default='off')
    with (CONTEXT / 'native-artifact-proof.json').open('x', encoding='utf-8') as out:
        json.dump(proof, out, sort_keys=True, indent=2)
        out.write('\n')
    print(f'PASS: ordered native/inherited sources, fallback, {len(graph)} reachable assets; {entry} => {page}, {css}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('before', 'legacy', 'assets'))
    args = parser.parse_args()
    manifest, targets = checked_context()
    if args.phase == 'before':
        before()
    elif args.phase == 'legacy':
        install_legacy()
        verify_legacy(manifest)
    else:
        assets(manifest, targets)


if __name__ == '__main__':
    main()
