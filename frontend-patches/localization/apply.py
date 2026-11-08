import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COMMIT = '36bd8859f2a6345a620477bc708d0546e8c3f08a'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def once(data, old, new):
    if data.count(old) != 1:
        raise ValueError('Expected source anchor is absent or ambiguous')
    return data.replace(old, new, 1)


def transform(target, data):
    if target == 'crm/www/crm.py':
        return once(data, b'\t\t\t"translated_messages": get_messages_for_boot(),\n',
                    b'\t\t\t"translated_messages": get_messages_for_boot(),\n\t\t\t"philosopher_language": frappe.local.lang,\n')
    if target == 'frontend/src/translation.js':
        data = once(data, b"import { getConfig } from 'frappe-ui'\n",
                    b"import { getConfig } from 'frappe-ui'\nimport chineseMessages from './philosopher-zh-cn.json'\n")
        data = once(data, b"  let translatedMessages = getConfig('translatedMessages') || {}\n",
                    b"  let translatedMessages = getConfig('translatedMessages') || {}\n"
                    b"  let language = String(window.philosopher_language || '').toLowerCase().replace(/_/g, '-')\n"
                    b"  let chinese = language === 'zh' || language === 'zh-cn' || language === 'zh-hans' || language.startsWith('zh-hans-')\n")
        data = once(data, b"    if (translatedMessages[key]) {\n      translatedMessage = translatedMessages[key]\n    }",
                    b"    if (translatedMessages[key] || (chinese && chineseMessages[key])) {\n      translatedMessage = translatedMessages[key] || chineseMessages[key]\n    }")
        return once(data, b"    translatedMessage = translatedMessages[message] || message\n",
                    b"    translatedMessage = translatedMessages[message] || (chinese && chineseMessages[message]) || message\n")
    raise ValueError('Unexpected transform target: ' + target)


def apply(root, mode='apply'):
    root = root.resolve(strict=True)
    if not (root / 'frontend').is_dir():
        raise ValueError('CRM root/frontend required')
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != COMMIT:
        raise ValueError('CRM HEAD mismatch')
    manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    changes = []
    for entry in manifest:
        target = root / entry['target']
        parent = target.parent.resolve(strict=True)
        if not parent.is_relative_to(root) or target.is_symlink():
            raise ValueError('Target escapes CRM root or is a symlink: ' + entry['target'])
        if target.exists() and target.stat().st_nlink != 1:
            raise ValueError('Hard-linked target refused: ' + entry['target'])
        current = target.read_bytes() if target.exists() else None
        expected = entry['after'] if mode == 'verify' else entry['before']
        if (digest(current) if current is not None else None) != expected:
            raise ValueError('Source mismatch: ' + entry['target'])
        if mode != 'verify':
            replacement = ((HERE / 'zh-CN.json').read_bytes() if entry['target'].endswith('/philosopher-zh-cn.json')
                           else transform(entry['target'], current))
            if digest(replacement) != entry['after']:
                raise ValueError('Replacement mismatch: ' + entry['target'])
            changes.append((target, replacement))
    if mode == 'apply':
        for target, data in changes:
            temporary = target.with_name(target.name + '.localization-tmp')
            with temporary.open('xb') as stream:
                stream.write(data)
            os.replace(temporary, target)
    return len(manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('crm_root', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    mode = 'check' if args.check else 'verify' if args.verify else 'apply'
    try:
        count = apply(args.crm_root, mode)
        print(f'Localization {mode}: {count} files verified')
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('LOCALIZATION REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)
