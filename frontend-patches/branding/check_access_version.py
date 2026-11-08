import ast
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('branding_access_version', HERE / 'access_version.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AccessVersionTests(unittest.TestCase):
    def test_generated_digest_follows_bytes_and_real_injection_keeps_response_contract(self):
        asset = b'(() => { /* final source bytes */ })()\n'
        receipt, updated = module.generate(asset)
        self.assertEqual(receipt['asset_sha256'], module.sha(asset))
        self.assertEqual(receipt['script_url'], '/assets/team_access/access.js?v=' + module.sha(asset))
        changed, _ = module.generate(asset + b'\n')
        self.assertNotEqual(receipt['script_url'], changed['script_url'])
        original = (HERE / 'fixtures/team_access__request.py').read_bytes()
        replacement = ('<script defer src="' + receipt['script_url'] + '"></script>').encode()
        self.assertEqual(updated.replace(replacement, module.ANCHOR, 1), original)
        tree = ast.parse(updated)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'after_request')
        source = ast.Module(body=[function], type_ignores=[])
        sanitize_calls = []
        responses = types.ModuleType('team_access.responses')
        responses.sanitize_response = lambda response: sanitize_calls.append(response)
        frappe = types.SimpleNamespace(local=types.SimpleNamespace(request=types.SimpleNamespace(path='/crm')))
        namespace = {'frappe': frappe}
        exec(compile(source, '<actual after_request>', 'exec'), namespace)
        class Response:
            def __init__(self, text, mimetype='text/html', status=200):
                self.text, self.mimetype, self.status_code = text, mimetype, status
                self.headers = {}
            def get_data(self, as_text=False):
                return self.text
            def set_data(self, value):
                self.text = value
        with patch.dict(sys.modules, {'team_access.responses': responses}):
            response = Response('<body>unchanged</body>')
            namespace['after_request'](response)
            self.assertEqual(response.text, '<body>unchanged' + replacement.decode() + '</body>')
            namespace['after_request'](response)
            self.assertEqual(response.text.count(replacement.decode()), 1)
            self.assertEqual(response.headers, {'Cache-Control': 'no-store, private', 'Pragma': 'no-cache'})
            frappe.local.request.path = '/api/method/example'
            api = Response('{"message":"unchanged"}', 'application/json')
            namespace['after_request'](api)
            self.assertEqual(api.text, '{"message":"unchanged"}')
            self.assertEqual(api.headers['Cache-Control'], 'no-store, private')
            frappe.local.request.path = '/crm'
            failed = Response('<body>denied</body>', status=403)
            namespace['after_request'](failed)
            self.assertEqual(failed.text, '<body>denied</body>')
            self.assertEqual(len(sanitize_calls), 4)

    def test_check_apply_verify_unknown_source_and_changed_asset_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            asset = root / module.ASSET
            target = root / module.TARGET
            asset.parent.mkdir(parents=True)
            asset.write_bytes(b'final actual access bytes')
            original = (HERE / 'fixtures/team_access__request.py').read_bytes()
            target.write_bytes(original)
            receipt, _ = module.generate(asset.read_bytes())
            module.apply(root, receipt, 'check')
            self.assertEqual(target.read_bytes(), original)
            module.apply(root, receipt)
            module.apply(root, receipt, 'verify')
            with self.assertRaises(ValueError):
                module.apply(root, receipt)
            after = target.read_bytes()
            asset.write_bytes(asset.read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                module.apply(root, receipt, 'verify')
            self.assertEqual(target.read_bytes(), after)
            asset.write_bytes(b'final actual access bytes')
            target.write_bytes(original + b'\n')
            with self.assertRaises(ValueError):
                module.apply(root, receipt)


if __name__ == '__main__':
    unittest.main()
