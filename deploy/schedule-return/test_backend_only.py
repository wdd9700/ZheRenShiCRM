import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest


HERE = Path(__file__).resolve().parent
SERVICES = ('db', 'redis-cache', 'redis-queue', 'frontend', 'scheduler', 'websocket',
            'queue-short', 'queue-long', 'configurator')
HARNESS = r'''
source deploy/schedule-return/backend-only.sh
runtime=$1
state=$1/state
mixed=$1
fixture=$1
shift
stable_dir() { [ "$1" = "$fixture" ] && [ -d "$1" ] && [ ! -L "$1" ]; }
raw_non_target_snapshot() { sed -e 's/\r$//' "$fixture/current"; }
backend_ip() { printf '172.18.0.7\n'; }
dns_matches() { [ "$1" = 172.18.0.7 ]; }
wait_backend() { :; }
ping() { :; }
trial() { [ "$*" = check ]; }
live_image() {
    if [ -f "$fixture/replaced" ]; then printf 'base\n'; else sed -n '1p' "$fixture/image"; fi
}
id_for() {
    case "$(live_image)" in
        base) printf '%064d\n' 1 ;;
        candidate) printf '%064d\n' 2 ;;
        other) printf '%064d\n' 3 ;;
        *) return 1 ;;
    esac
}
image_is() {
    [ "$1" = "$back" ] || [ "$1" = "$(id_for)" ] || return 1
    case "$(live_image)" in
        base) [ "$2" = "$base" ] ;;
        candidate) [ "$2" = "$new" ] ;;
        *) return 1 ;;
    esac
}
html_is() {
    [ ! -e "$fixture/wrong-html" ] && [ "${2:-$back}" = "$(id_for)" ] || return 1
    case "$(live_image)" in
        base) [ "$1" = "$old_html" ] ;;
        candidate) [ "$1" = "$new_html" ] ;;
        *) return 1 ;;
    esac
}
compose() {
    [ "$*" = 'up -d --no-deps --pull never --no-build --force-recreate backend' ] || return 1
    [ ! -e "$fixture/replaced" ] || return 1
    printf '%s\n' "$*" > "$fixture/replaced"
    if [ -f "$fixture/during" ]; then cp "$fixture/during" "$fixture/current"; fi
}
docker() {
    [ "$1" = inspect ] && [ "$2" = --format ] || return 1
    case "$3" in
        '{{.Id}}') [ "$4" = "$back" ] && id_for ;;
        '{{.State.Health.Status}}')
            if [ -f "$fixture/unhealthy" ] && [ "$4" = "$front" ]; then printf 'unhealthy\n'; else printf 'healthy\n'; fi ;;
        '{{.State.Status}} {{.State.OOMKilled}}') printf 'running false\n' ;;
        '{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}') printf 'exited 0 false\n' ;;
        '{{.Name}} {{.Id}} {{.State.StartedAt}} {{.Image}}') [ "$4" = "$front" ] ;;
        *) return 1 ;;
    esac
}
case "$1" in
    init)
        printf 'ready image=%s\n' "$base" > "$mixed/state.before"
        state_write "backend-only active base=$base candidate=$new override=$mixed/backend.yml"
        non_target_snapshot > "$mixed/non-target.before"
        ;;
    awaiting-switch)
        state_write "backend-only awaiting-https base=$base candidate=$new override=$mixed/backend.yml"
        ;;
    interrupted)
        case "$2" in
            rollback|rollback-planned) state_write "backend-only $2 base=$base candidate=$new" ;;
            active) : ;;
            *) exit 1 ;;
        esac
        if [ "$2" != rollback ]; then capture_rollback_window; fi
        ;;
    *) dispatch "$@" ;;
esac
'''


def snapshot(service=None, key=None, value=None, tick='100'):
    lines = []
    for index, name in enumerate(SERVICES):
        entry = dict(id='id' + str(index), image='img' + str(index), started='2026-11-18T12:00:00Z',
                     status='exited' if name == 'configurator' else 'running', pid='0' if name == 'configurator' else '10',
                     exit='0', restart='0', oom='false', config='cfg' + str(index),
                     mounts=[dict(Name='sites', Destination='/sites', RW=True),
                             dict(Name='logs', Destination='/logs', RW=True)],
                     net=dict(ip='172.18.0.' + str(index + 2)))
        if name == service:
            if key == 'lifecycle':
                entry.update(started='2026-11-18T12:30:00Z', pid='99', restart='1')
            elif key == 'RW':
                entry['mounts'][0]['RW'] = value
            elif key == 'mount_order':
                entry['mounts'].reverse()
            else:
                entry[key] = value
        entry['mounts'] = json.dumps(entry['mounts'])
        entry['net'] = json.dumps(entry['net'])
        lines.append('/crm-trial-c010400-' + name + '-1 ' + ' '.join(entry.values()))
    lines += ['logs', 'sites', 'netid [{"Subnet":"172.18.0.0/16"}]', '1000', tick]
    return '\n'.join(lines) + '\n'


class BackendOnlyRollback(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(dir=HERE)
        self.addCleanup(directory.cleanup)
        self.fixture = Path(directory.name)
        self.write('current', snapshot())
        self.write('image', 'candidate\n')
        self.call('init')
        self.original = (self.fixture / 'non-target.before').read_bytes()
        self.active = (self.fixture / 'state').read_bytes()

    def write(self, name, content):
        (self.fixture / name).write_bytes(content.encode('utf-8'))

    def call(self, *args, success=True):
        # Relative fixture path avoids Windows drive-letter differences in Bash.
        fixture = self.fixture.relative_to(HERE.parents[1]).as_posix()
        result = subprocess.run(['bash', '-s', '--', fixture, *args], input=HARNESS.encode('utf-8'),
                                cwd=HERE.parents[1], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output = result.stdout.decode('utf-8', errors='replace')
        self.assertEqual(result.returncode == 0, success, output)
        return output

    def assert_not_started(self):
        self.assertEqual((self.fixture / 'state').read_bytes(), self.active)
        self.assertFalse((self.fixture / 'rollback-window.before').exists())
        self.assertFalse((self.fixture / 'replaced').exists())
        self.assertEqual((self.fixture / 'non-target.before').read_bytes(), self.original)

    def test_planned_window_accepts_healthy_same_id_restart(self):
        self.write('current', snapshot('websocket', 'lifecycle'))
        self.call('rollback', '--confirm-exclusive')
        self.assertTrue((self.fixture / 'replaced').is_file())
        self.assertIn(b'rollback-planned-awaiting-https', (self.fixture / 'state').read_bytes())
        frozen = (self.fixture / 'rollback-window.before').read_bytes()
        self.assertNotEqual(frozen, self.original)
        self.call('accept-rollback', success=False)
        self.call('accept-rollback', '--confirm-https')
        self.assertEqual((self.fixture / 'state').read_bytes(), (self.fixture / 'state.before').read_bytes())
        self.assertEqual((self.fixture / 'non-target.before').read_bytes(), self.original)
        self.assertEqual((self.fixture / 'rollback-window.before').read_bytes(), frozen)

    def test_frontend_master_tick_only_does_not_change_stable_identity(self):
        self.write('current', snapshot('frontend', 'lifecycle', tick='999'))
        self.call('rollback', '--confirm-exclusive')
        self.call('accept-rollback', '--confirm-https')

    def test_unsorted_mounts_still_compare_equal(self):
        self.write('current', snapshot('websocket', 'mount_order'))
        self.call('rollback', '--confirm-exclusive')
        self.call('accept-rollback', '--confirm-https')

    def test_planned_window_requires_confirmation_and_health(self):
        self.assertIn('planned rollback requires', self.call('rollback', success=False))
        self.assert_not_started()
        self.write('unhealthy', '')
        self.assertIn('cannot start planned rollback window', self.call('rollback', '--confirm-exclusive', success=False))
        self.assert_not_started()

    def test_planned_rejects_identity_or_resource_drift(self):
        cases = [snapshot('frontend', 'id', 'replacement'), snapshot('frontend', 'image', 'other-image'),
                 snapshot('websocket', 'config', 'new-hash'), snapshot('websocket', 'RW', False),
                 snapshot('db', 'net', {'ip': '172.18.0.99'}), snapshot('websocket', 'oom', 'true'),
                 snapshot('configurator', 'exit', '1'), snapshot().replace('netid ', 'other-net '),
                 snapshot().replace('\nsites\n', '\nother-volume\n'), snapshot().replace('\n1000\n', '\n0\n')]
        for current in cases:
            with self.subTest(current=current):
                self.write('current', current)
                output = self.call('rollback', '--confirm-exclusive', success=False)
                self.assertIn('non-target stable identity differs', output)
                self.assert_not_started()

    def test_change_during_window_is_not_rebased(self):
        self.write('during', snapshot('websocket', 'lifecycle'))
        self.call('rollback', '--confirm-exclusive', success=False)
        self.assertIn(b'rollback-planned-failed', (self.fixture / 'state').read_bytes())
        self.call('rollback', '--confirm-exclusive', success=False)
        self.call('accept-rollback', '--confirm-https', success=False)
        self.assertEqual((self.fixture / 'rollback-window.before').read_bytes(), self.original)

    def test_change_before_https_confirmation_blocks_ready(self):
        self.call('rollback', '--confirm-exclusive')
        self.write('current', snapshot('websocket', 'lifecycle'))
        self.call('accept-rollback', '--confirm-https', success=False)
        self.assertIn(b'rollback-planned-awaiting-https', (self.fixture / 'state').read_bytes())

    def test_interrupted_release_rollback_resumes_on_candidate(self):
        self.call('interrupted', 'rollback')
        self.call('accept-rollback', '--confirm-https', success=False)
        self.call('rollback')
        self.assertTrue((self.fixture / 'replaced').exists())
        self.assertIn(b'rollback-awaiting-https', (self.fixture / 'state').read_bytes())
        self.call('accept-rollback', '--confirm-https')

    def test_interrupted_planned_rollback_reuses_sealed_window(self):
        self.write('current', snapshot('websocket', 'lifecycle'))
        self.call('interrupted', 'active')
        frozen = (self.fixture / 'rollback-window.before').read_bytes()
        self.write('current', snapshot())
        self.assertIn('snapshot drifted', self.call('rollback', '--confirm-exclusive', success=False))
        self.assertEqual((self.fixture / 'state').read_bytes(), self.active)
        self.write('current', snapshot('websocket', 'lifecycle'))
        self.call('rollback', '--confirm-exclusive')
        self.assertEqual((self.fixture / 'rollback-window.before').read_bytes(), frozen)
        self.call('accept-rollback', '--confirm-https')

    def test_interrupted_planned_marker_resumes_on_candidate(self):
        self.call('interrupted', 'rollback-planned')
        self.call('rollback', '--confirm-exclusive')
        self.assertTrue((self.fixture / 'replaced').exists())
        self.assertEqual((self.fixture / 'rollback-window.before').read_bytes(), self.original)
        self.assertIn(b'rollback-planned-awaiting-https', (self.fixture / 'state').read_bytes())
        self.call('accept-rollback', '--confirm-https')

    def assert_restored_backend_needs_https(self, phase, *args):
        self.call('interrupted', phase)
        self.write('image', 'base\n')
        self.call('accept-rollback', '--confirm-https', success=False)
        self.call('rollback', *args)
        self.assertFalse((self.fixture / 'replaced').exists())
        self.assertIn((phase + '-awaiting-https').encode(), (self.fixture / 'state').read_bytes())
        self.call('accept-rollback', success=False)
        self.call('accept-rollback', '--confirm-https')
        self.assertEqual((self.fixture / 'state').read_bytes(), (self.fixture / 'state.before').read_bytes())

    def test_interrupted_release_with_base_backend_does_not_replace(self):
        self.assert_restored_backend_needs_https('rollback')

    def test_interrupted_planned_with_base_backend_does_not_replace(self):
        self.assert_restored_backend_needs_https('rollback-planned', '--confirm-exclusive')

    def test_interrupted_rollback_rejects_missing_or_wrong_backend(self):
        self.call('interrupted', 'rollback-planned')
        for actual, wrong_html in [('other', False), ('missing', False), ('candidate', True), ('base', True)]:
            with self.subTest(actual=actual):
                self.write('image', actual + '\n')
                if wrong_html:
                    self.write('wrong-html', '')
                self.call('rollback', '--confirm-exclusive', success=False)
                self.assertIn(b'rollback-planned-failed', (self.fixture / 'state').read_bytes())
                self.assertFalse((self.fixture / 'replaced').exists())
                self.assertEqual((self.fixture / 'rollback-window.before').read_bytes(), self.original)
        self.call('accept-rollback', '--confirm-https', success=False)

    def test_release_window_stays_strict(self):
        self.call('awaiting-switch')
        self.write('current', snapshot('websocket', 'lifecycle'))
        self.call('rollback', '--confirm-exclusive', success=False)
        self.call('rollback', success=False)
        self.assertIn(b'backend-only rollback-failed', (self.fixture / 'state').read_bytes())
        self.assertFalse((self.fixture / 'rollback-window.before').exists())
        self.assertFalse((self.fixture / 'replaced').exists())


if __name__ == '__main__':
    unittest.main()
