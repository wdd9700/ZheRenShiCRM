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


def transform(target, data):
    replacements = {
        'frontend/src/components/Notifications.vue': [
            ('title="No New Notifications"', ':title="__(\'No New Notifications\')"'),
            ('description="You have no new notifications"', ':description="__(\'You have no new notifications\')"'),
        ],
        'frontend/src/components/Activities/DataFields.vue': [
            ('label="Save"', ':label="__(\'Save\')"'),
        ],
        'frontend/src/components/Filter.vue': [
            ("const filterFieldOptions = computed(() => {\n  const fields = filterableFields.data || []",
             """const systemFilterLabels = {
  'CRM Lead': {
    company_description: 'Company Description', lead_score: 'Lead Score',
    lead_temperature: 'Lead Temperature', lead_owner: 'Lead Owner',
    first_response_time: 'First Response Time', first_responded_on: 'First Responded On',
    last_response_time: 'Last Response Time', last_responded_on: 'Last Responded On',
    communication_status: 'Communication Status', response_by: 'Response By',
    sla_creation: 'SLA Creation', sla_status: 'SLA Status',
    annual_revenue: 'Annual Revenue', no_of_employees: 'No. of Employees',
    middle_name: 'Middle Name', mobile_no: 'Mobile No.',
    converted: 'Converted', lost_reason: 'Lost Reason', lost_notes: 'Lost Notes',
    territory: 'Territory', total: 'Total', net_total: 'Net Total',
  },
  'CRM Deal': {
    company_description: 'Company Description', deal_owner: 'Deal Owner',
    first_response_time: 'First Response Time', first_responded_on: 'First Responded On',
    last_response_time: 'Last Response Time', last_responded_on: 'Last Responded On',
    communication_status: 'Communication Status', response_by: 'Response By',
    sla_creation: 'SLA Creation', sla_status: 'SLA Status',
    annual_revenue: 'Annual Revenue', no_of_employees: 'No. of Employees',
    next_step: 'Next Step', lead_name: 'Lead Name', organization_name: 'Organization Name',
    email: 'Primary email', mobile_no: 'Primary mobile no', phone: 'Primary phone',
    deal_value: 'Deal Value', expected_deal_value: 'Expected Deal Value',
    expected_closure_date: 'Expected Closure Date', closed_date: 'Closed Date',
    currency: 'Currency', exchange_rate: 'Exchange Rate', lost_reason: 'Lost Reason',
    lost_notes: 'Lost Notes', territory: 'Territory', total: 'Total', net_total: 'Net Total',
  },
}

const filterFieldOptions = computed(() => {
  const systemLabels = systemFilterLabels[props.doctype] || {}
  const fields = (filterableFields.data || []).map((field) =>
    !field.is_custom_field && !field.custom &&
    systemLabels[field.fieldname] && field.label === systemLabels[field.fieldname]
      ? { ...field, label: __(field.label) }
      : field,
  )"""),
            ('        label: o,\n        value: o,', "        label: fieldtype == 'Check' ? __(o) : o,\n        value: o,"),
        ],
        'frontend/src/components/IconPicker.vue': [
            ('placeholder="Search by keyword"', ':placeholder="__(\'Search by keyword\')"'),
            ('<Button @click="setRandom">Random</Button>', '<Button @click="setRandom">{{ __(\'Random\') }}</Button>'),
            ('{{ group }}', "{{ group === 'No results' ? __('No results') : group }}"),
        ],
    }
    if target not in replacements:
        raise ValueError('Unexpected target: ' + target)
    for old, new in replacements[target]:
        old, new = old.encode('utf-8'), new.encode('utf-8')
        if data.count(old) != 1:
            raise ValueError('Expected source anchor absent or ambiguous: ' + old.decode('utf-8'))
        data = data.replace(old, new, 1)
    return data


def apply(root, mode='apply'):
    root = root.resolve(strict=True)
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if head != COMMIT:
        raise ValueError('CRM HEAD mismatch')
    entries = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
    changes = []
    for entry in entries:
        target = root / entry['target']
        if not target.parent.resolve(strict=True).is_relative_to(root) or target.is_symlink():
            raise ValueError('Target escapes CRM root or is a symlink: ' + entry['target'])
        if target.stat().st_nlink != 1:
            raise ValueError('Hard-linked target refused: ' + entry['target'])
        source = target.read_bytes()
        if digest(source) != entry['after' if mode == 'verify' else 'before']:
            raise ValueError('Source mismatch: ' + entry['target'])
        if mode != 'verify':
            output = transform(entry['target'], source)
            if digest(output) != entry['after']:
                raise ValueError('Replacement mismatch: ' + entry['target'])
            temporary = target.with_name(target.name + '.common-ui-localization-tmp')
            backup = target.with_name(target.name + '.common-ui-localization-backup')
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
    parser.add_argument('crm_root', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    try:
        mode = 'check' if args.check else 'verify' if args.verify else 'apply'
        print(f'Common UI localization {mode}: {apply(args.crm_root, mode)} files verified')
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print('COMMON UI LOCALIZATION REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)
