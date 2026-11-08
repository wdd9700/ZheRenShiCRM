import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
PREFIX = 'ui/src/components/Onboarding/'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def once(data, old, new):
    old, new = old.encode('utf-8'), new.encode('utf-8')
    if data.count(old) != 1:
        raise ValueError('Expected source anchor absent or ambiguous: ' + old.decode('utf-8'))
    return data.replace(old, new, 1)


TRANSLATOR = '''const translate = getCurrentInstance()?.appContext.config.globalProperties.__ ??
	((message: string, values: unknown[] = []) =>
		message.replace(/\\{(\\d+)\\}/g, (match, index) => String(values[Number(index)] ?? match)));

'''


def transform(target, data):
    name = Path(target).name
    replacements = {
        'GettingStartedBanner.vue': [
            ('theme="blue"', 'theme="gray"\n\t\t\tvariant="subtle"'),
            ('{{ "Getting started" }}', '{{ translate("Getting started") }}'),
            ('{{ `${stepsCompleted}/${totalSteps} steps` }}', '{{ translate("{0}/{1} steps", [stepsCompleted, totalSteps]) }}'),
            ('{{ "You are all set" }}', '{{ translate("You are all set") }}'),
            ('{{ "All steps are completed successfully" }}', '{{ translate("All steps are completed successfully") }}'),
            (":label=\"stepsCompleted == 0 ? 'Start now' : 'Continue'\"", ":label=\"translate(stepsCompleted == 0 ? 'Start now' : 'Continue')\""),
            ('aria-label="Getting started"', ':aria-label="translate(\'Getting started\')"'),
            ('import { Button } from "frappe-ui";', 'import { Button } from "frappe-ui";\nimport { getCurrentInstance } from "vue";'),
            ('const props = withDefaults', TRANSLATOR + 'const props = withDefaults'),
        ],
        'HelpModal.vue': [
            ('aria-label="More options"', ':aria-label="translate(\'More options\')"'),
            (":aria-label=\"minimize ? 'Maximize' : 'Minimize'\"", ":aria-label=\"translate(minimize ? 'Maximize' : 'Minimize')\""),
            ('aria-label="Close"', ':aria-label="translate(\'Close\')"'),
            ('import { computed, watch } from "vue";', 'import { computed, getCurrentInstance, watch } from "vue";'),
            ('const props = withDefaults', TRANSLATOR + 'const props = withDefaults'),
            ('return "Getting started";', 'return translate("Getting started");'),
            ('return "Help center";', 'return translate("Help center");'),
            ('label: "Reset onboarding steps",', 'label: translate("Reset onboarding steps"),'),
            ('label: "Help centre",', 'label: translate("Help centre"),'),
            ('label: "Getting started",', 'label: translate("Getting started"),'),
        ],
        'OnboardingSteps.vue': [
            ('{{ "Welcome to " + title }}', '{{ translate("Welcome to {0}", [translate(title)]) }}'),
            ('{{ `${stepsCompleted}/${totalSteps} steps completed` }}', '{{ translate("{0}/{1} steps completed", [stepsCompleted, totalSteps]) }}'),
            (':label="`${completedPercentage}% completed`"', ':label="translate(\'{0}% completed\', [completedPercentage])"'),
            (':label="\'Reset all\'"', ':label="translate(\'Reset all\')"'),
            (':label="\'Skip all\'"', ':label="translate(\'Skip all\')"'),
            (':label="\'Skip\'"', ':label="translate(\'Skip\')"'),
            (':label="\'Reset\'"', ':label="translate(\'Reset\')"'),
            ('import { Badge, Button, Tooltip } from "frappe-ui";', 'import { Badge, Button, Tooltip } from "frappe-ui";\nimport { getCurrentInstance } from "vue";'),
            ('const props = withDefaults', TRANSLATOR + 'const props = withDefaults'),
            ('return `You need to complete "${dependsOnStep.title}" first.`;', 'return translate(\'You need to complete "{0}" first.\', [dependsOnStep.title]);'),
        ],
    }
    if name not in replacements or target != PREFIX + name:
        raise ValueError('Unexpected target: ' + target)
    for old, new in replacements[name]:
        data = once(data, old, new)
    return data


def apply(root, mode='apply'):
    root = root.resolve(strict=True)
    entries = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    changes = []
    for entry in entries:
        target = root / entry['target']
        if not target.parent.resolve(strict=True).is_relative_to(root) or target.is_symlink():
            raise ValueError('Target escapes Framework root or is a symlink: ' + entry['target'])
        if target.stat().st_nlink != 1:
            raise ValueError('Hard-linked target refused: ' + entry['target'])
        source = target.read_bytes()
        if digest(source) != entry['after' if mode == 'verify' else 'before']:
            raise ValueError('Source mismatch: ' + entry['target'])
        if mode != 'verify':
            output = transform(entry['target'], source)
            if digest(output) != entry['after']:
                raise ValueError('Replacement mismatch: ' + entry['target'])
            temporary = target.with_name(target.name + '.onboarding-localization-tmp')
            backup = target.with_name(target.name + '.onboarding-localization-backup')
            changes.append((target, source, output, temporary, backup))
    for _, _, _, temporary, backup in changes:
        if os.path.lexists(temporary) or os.path.lexists(backup):
            raise ValueError('Temporary path already exists')
    if mode == 'apply':
        owned, committed, preserve = set(), [], set()
        try:
            for _, source, output, temporary, backup in changes:
                for path, content in ((temporary, output), (backup, source)):
                    with path.open('xb') as stream:
                        owned.add(path)
                        stream.write(content)
            for target, _, _, temporary, backup in changes:
                os.replace(temporary, target)
                owned.remove(temporary)
                committed.append((target, backup))
        except BaseException as error:
            failures = []
            for target, backup in reversed(committed):
                try:
                    os.replace(backup, target)
                    owned.remove(backup)
                except OSError as rollback_error:
                    preserve.add(backup)
                    failures.append(f'{target}: {rollback_error}')
            if failures:
                raise RuntimeError('Rollback incomplete; originals retained: ' + '; '.join(failures)) from error
            raise
        finally:
            for path in owned - preserve:
                path.unlink(missing_ok=True)
    return len(entries)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('framework_root', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    try:
        mode = 'check' if args.check else 'verify' if args.verify else 'apply'
        print(f'Onboarding localization {mode}: {apply(args.framework_root, mode)} files verified')
    except (ValueError, OSError, RuntimeError) as error:
        print('ONBOARDING LOCALIZATION REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)
