import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import contract
import prepare
import verify


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup((temp := tempfile.TemporaryDirectory(dir=Path(__file__).parent)).cleanup)
        self.root = Path(temp.name)
        self.assets = self.root / 'assets'
        self.frontend = self.assets / 'crm/frontend'
        self.html = self.root / 'crm.html'
        self.old_module = '/assets/crm/frontend/assets/index-OLD.js'
        self.html.write_text('''<title>哲人石CRM</title><script>boot.philosopher_language</script>
<link rel="stylesheet" href="/assets/crm/frontend/assets/base-123.css">
<script type="module" src="/assets/crm/frontend/assets/index-NEW.js"></script>''', encoding='utf-8')
        self.route = '''r=[{path:"/team-schedule",name:"TeamSchedule",component:()=>p(()=>import("./TeamSchedule-ABC.js"),[0])}];const d=["assets/TeamSchedule-ABC.css"];'''
        self.put('assets/index-NEW.js', 'import "./router-456.js";')
        self.put('assets/router-456.js', self.route)
        self.put('assets/base-123.css', 'body{display:block}')
        self.put('assets/TeamSchedule-ABC.js', 'export default {label:"团队日程",method:"team_schedule.availability.api.busy_free"};')
        self.put('assets/TeamSchedule-ABC.css', '.team-schedule{display:grid}')
        self.put('manifest.webmanifest', json.dumps({'name': '哲人石CRM', 'short_name': '哲人石CRM'}))

    def put(self, name, data):
        path = self.frontend / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data, encoding='utf-8')

    def check(self):
        return verify.verify_bundle(self.html, self.assets, self.old_module)

    def test_valid_reachable_vite_artifact(self):
        graph, entry, page, css = self.check()
        self.assertIn('assets/router-456.js', graph)
        self.assertTrue(entry.endswith('index-NEW.js'))
        self.assertEqual((page, css), ('assets/TeamSchedule-ABC.js', 'assets/TeamSchedule-ABC.css'))

    def test_old_module_rejected(self):
        self.old_module = '/assets/crm/frontend/assets/index-NEW.js'
        with self.assertRaisesRegex(RuntimeError, 'New, branded'):
            self.check()

    def test_unlinked_page_rejected(self):
        self.put('assets/router-456.js', 'const label="团队日程";')
        with self.assertRaisesRegex(RuntimeError, 'does not link'):
            self.check()

    def test_css_and_html_dependency_required(self):
        (self.frontend / 'assets/TeamSchedule-ABC.css').unlink()
        with self.assertRaises(FileNotFoundError):
            self.check()
        (self.frontend / 'assets/base-123.css').unlink()
        with self.assertRaisesRegex(RuntimeError, 'Missing CRM HTML dependency'):
            self.check()

    def test_diagnostics_rejected(self):
        self.put('assets/router-456.js', self.route + 'const mode="D020102";')
        with self.assertRaisesRegex(RuntimeError, 'Temporary read diagnostics'):
            self.check()


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup((temp := tempfile.TemporaryDirectory(dir=Path(__file__).parent)).cleanup)
        self.runtime = Path(temp.name)
        self.context = self.runtime / ('native-schedule-' + 'a' * 32)
        self.context.mkdir()
        self.s020, self.s021 = '1' * 40, '2' * 40
        inputs = {'app-source/team_schedule/' + name: ('100644', name.encode()) for name in contract.NATIVE_INPUTS}
        manifest = {
            'crm_commit': contract.CRM_HEAD,
            'app_sources': {name: contract.sha(name.encode()) for name in contract.NATIVE_INPUTS},
            'targets': [{'target': name, 'before': ('a' * 64 if name in contract.EXISTING_CRM_TARGETS else None), 'after': 'b' * 64}
                        for name in sorted(contract.EXISTING_CRM_TARGETS | contract.NEW_CRM_TARGETS)],
        }
        self.sources = dict(inputs, **{contract.PATCH + 'manifest.json': ('100644', json.dumps(manifest).encode())})
        self.files = prepare.write_sources(self.sources, self.context)
        self.receipt = self.write_receipt(self.files)
        self.addCleanup(patch.stopall)
        patch.object(prepare, 'RUNTIME', self.runtime).start()
        patch.object(prepare, 'sources', return_value=self.sources).start()

    def write_receipt(self, files):
        raw = json.dumps(prepare.source_manifest(self.s020, self.s021, files)).encode()
        (self.context / contract.RECEIPT).write_bytes(raw)
        return contract.sha(raw)

    def test_receipt_checks_exact_source(self):
        prepare.load(self.context, self.receipt)
        before = self.context / 'app-source/team_schedule' / contract.HTML
        before.write_bytes(b'drift')
        with self.assertRaisesRegex(RuntimeError, 'Changed native build source'):
            prepare.load(self.context, self.receipt)
        tampered = dict(self.files, **{'app-source/team_schedule/' + contract.HTML: contract.sha(b'drift')})
        with self.assertRaisesRegex(RuntimeError, 'exact Git source identity'):
            prepare.load(self.context, self.write_receipt(tampered))

    def test_extra_file_rejected(self):
        (self.context / 'extra').touch()
        with self.assertRaisesRegex(RuntimeError, 'unmanifested'):
            prepare.load(self.context, self.receipt)

    def test_bad_crm_target_rejected(self):
        path = self.context / (contract.PATCH + 'manifest.json')
        value = json.loads(path.read_bytes())
        value['targets'].append(dict(target='crm/hooks.py', before='a' * 64, after='b' * 64))
        path.write_text(json.dumps(value), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'target whitelist'):
            contract.patch_contract(self.context, self.files)

    def test_wrong_parent_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Exact e14b6/c260'):
            prepare.verify_base(dict(Id=contract.BASE_CONFIG, Os='linux', Architecture='amd64', RootFS=dict(Layers=['sha256:' + '1' * 64] * 16)))


if __name__ == '__main__':
    unittest.main()
