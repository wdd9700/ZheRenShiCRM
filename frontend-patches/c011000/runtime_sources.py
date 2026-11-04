import hashlib
import json
from pathlib import Path

from source_edits import SOURCE_EDITS, transform

SIDEBAR = 'frontend/src/components/Layouts/AppSidebar.vue'
NAV_MANIFEST_SHA = '74787afa31373457e9b91fa8ea6f53e4e3317854670656558579df0762b75670'
NAV_AFTER = 'e169f9d13cec9245390a8854b1dba8026227945abcaac03fb097473fca29a852'
HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def navigation_contract(entry, manifest_data=None):
    data = manifest_data if manifest_data is not None else (HERE / 'runtime-evidence/l3-scheduling-4ff499e.json').read_bytes()
    if sha(data) != NAV_MANIFEST_SHA:
        raise ValueError('Runtime navigation manifest drift')
    manifest = json.loads(data)
    overlap = manifest['upstream_overlap']
    target, = manifest['targets']
    baseline, = [item for item in target['baselines'] if item['name'] == 'c011000-resume']
    if (overlap['target'] != SIDEBAR or target['target'] != SIDEBAR
            or overlap['c011000_before'] != entry['before']
            or overlap['c011000_after'] != entry['after']
            or baseline['before'] != entry['after'] or baseline['after'] != NAV_AFTER
            or len(target['edits']) != 3):
        raise ValueError('Runtime navigation overlap drift')
    return target['edits']


def normalize_source(target, data, entry, manifest_data=None):
    digest = sha(data)
    if digest == entry['before']:
        data = transform(target, data)
    elif digest == entry['after']:
        pass
    elif target == SIDEBAR and digest == NAV_AFTER:
        restored = data.decode('utf-8')
        for edit in reversed(navigation_contract(entry, manifest_data)):
            if restored.count(edit['replacement']) != 1:
                raise ValueError('Runtime navigation replacement drift')
            restored = restored.replace(edit['replacement'], edit['anchor'])
        if sha(restored.encode('utf-8')) != entry['after']:
            raise ValueError('Runtime navigation resume guard drift')
        if "import { accountBoundary }" not in restored or "accountBoundary.state === 'HYDRATING'" not in restored:
            raise ValueError('Runtime navigation missing resume guard')
        return data
    else:
        raise ValueError('Runtime source evidence drift: ' + target)
    if sha(data) != entry['after']:
        raise ValueError('Runtime transformed source drift: ' + target)
    return data


def load_sources(frontend):
    manifest = {entry['target']: entry for entry in json.loads((HERE / 'manifest.json').read_text())}
    root = Path(frontend).parent
    return {target: normalize_source(target, (root / target).read_bytes(), manifest[target]).decode('utf-8')
            for target in SOURCE_EDITS}


if __name__ == '__main__':
    import sys
    print(json.dumps(load_sources(sys.argv[1])))
