import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manage = load("manage")
inner = load("prepare_inner")
TEMPLATE = '''map $http_x_forwarded_proto $proxy_x_forwarded_proto {
    default $scheme;
    https https;
}
server {
    listen ${NGINX_LISTEN_PORT};
    location /socket.io {
        proxy_set_header X-Frappe-Site-Name ${FRAPPE_SITE_NAME_HEADER};
        proxy_set_header Origin $proxy_x_forwarded_proto://${FRAPPE_SITE_NAME_HEADER};
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_pass http://socketio-server;
    }
    location @webserver {
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_pass http://backend-server;
    }
}
'''


class InnerTests(unittest.TestCase):
    def test_exact_two_changes_and_unrelated_template_update_preserved(self):
        after = inner.patch(TEMPLATE + "# future image setting\n")
        self.assertIn("Origin $proxy_x_forwarded_proto://$http_host;", after)
        self.assertIn("X-Forwarded-For $http_x_forwarded_for;", after)
        self.assertIn("X-Forwarded-For $proxy_add_x_forwarded_for;", after)
        self.assertTrue(after.endswith("# future image setting\n"))
        reverse = after.replace("Origin $proxy_x_forwarded_proto://$http_host;", "Origin $proxy_x_forwarded_proto://${FRAPPE_SITE_NAME_HEADER};")
        reverse = reverse.replace("X-Forwarded-For $http_x_forwarded_for;", "X-Forwarded-For $remote_addr;")
        self.assertEqual(reverse, TEMPLATE + "# future image setting\n")

    def test_template_drift_fails_closed(self):
        for content in (TEMPLATE.replace("https https;", ""), TEMPLATE.replace("Origin", "Different"),
                        TEMPLATE + "proxy_set_header X-Forwarded-For $remote_addr;", inner.patch(TEMPLATE)):
            with self.subTest(content=content), self.assertRaises(ValueError):
                inner.patch(content)

    def test_real_cli_no_overwrite(self):
        import sys
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            source, target = Path(temporary) / "template", Path(temporary) / "out"
            source.write_text(TEMPLATE)
            result = subprocess.run([sys.executable, str(HERE / "prepare_inner.py"), str(source), str(target)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(), inner.patch(TEMPLATE))
            again = subprocess.run([sys.executable, str(HERE / "prepare_inner.py"), str(source), str(target)], capture_output=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(target.read_text(), inner.patch(TEMPLATE))


class AcmeTests(unittest.TestCase):
    def test_isolated_environments_and_explicit_ca(self):
        for environment in ("staging", "production"):
            args = manage.certbot_args(environment)
            self.assertIn(f"type=bind,src=/etc/crm-acme/{environment},dst=/etc/letsencrypt", args)
            ca = args[args.index("--server") + 1]
            self.assertEqual("staging" in ca, environment == "staging")
            self.assertIn("/dev/null", args)
            self.assertIn(manage.CERTBOT_IMAGE, args)
            self.assertIn("--pull=never", args)
            self.assertIn("--read-only", args)
            self.assertIn("--cap-drop=ALL", args)
            self.assertIn("--security-opt=no-new-privileges", args)
            self.assertNotIn("--privileged", args)
            self.assertNotIn("--publish", args)
            mounts = [args[i + 1] for i, arg in enumerate(args) if arg == "--mount"]
            self.assertEqual(len(mounts), 4)
            self.assertFalse(any("docker.sock" in item or "src=/," in item for item in mounts))
        with self.assertRaises(ValueError):
            manage.certbot_args("../production")

    def test_issue_parameters_and_production_host_deploy(self):
        for environment in ("staging", "production"):
            with patch.object(manage, "check_certbot"), patch.object(manage, "prepare_acme"), patch.object(manage, "run") as run, patch.object(manage, "deploy_production") as deploy:
                manage.issue(environment, "ops@example.invalid")
            args = run.call_args.args
            self.assertIn("--ip-address", args)
            self.assertIn(manage.IP, args)
            self.assertIn("--required-profile", args)
            self.assertIn("shortlived", args)
            self.assertIn("--keep-until-expiring", args)
            self.assertNotIn("--force-renewal", args)
            self.assertNotIn("--deploy-hook", args)
            self.assertEqual(deploy.call_count, int(environment == "production"))

    def test_version_gate(self):
        for version, accepted in (("5.3.0", False), ("5.4.0", True), ("5.9.0", True), ("6.0.0", True)):
            with patch.object(manage, "run", return_value=f"certbot {version}\n".encode()):
                if accepted:
                    manage.check_certbot()
                else:
                    with self.assertRaises(RuntimeError):
                        manage.check_certbot()

    def test_failed_nginx_test_does_not_reload(self):
        with patch.object(manage, "certificate_check"), patch.object(manage, "run", side_effect=RuntimeError("invalid config")) as run:
            with self.assertRaises(RuntimeError):
                manage.reload_nginx()
            self.assertEqual(run.call_args_list[0].args, ("nginx", "-t"))
            self.assertEqual(run.call_count, 1)

    def test_deploy_order(self):
        events = []
        with patch.object(manage, "certificate_check", side_effect=lambda *_: events.append("cert")), patch.object(manage, "run", side_effect=lambda *args: events.append(args)), patch.object(manage, "served_check", side_effect=lambda: events.append("served")):
            manage.reload_nginx()
        self.assertEqual(events, ["cert", ("nginx", "-t"), ("systemctl", "reload", "nginx"), "served"])

    def test_config_failure_restores_without_reload(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            config = Path(temporary) / "active.conf"
            before = (manage.MARKER + "old config\n").encode()
            config.write_bytes(before)
            with patch.object(manage, "CONFIG", config), patch.object(manage, "STATE", Path(temporary)), patch.object(manage, "state_directory"), patch.object(manage, "run", side_effect=RuntimeError("nginx test failed")) as run:
                with self.assertRaises(RuntimeError):
                    manage.config_install(True)
            self.assertEqual(config.read_bytes(), before)
            self.assertEqual(run.call_count, 1)
            self.assertEqual((Path(temporary) / "rollback.conf").read_bytes(), before)

    def test_unmanaged_config_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            config = Path(temporary) / "active.conf"
            config.write_text("operator owned\n")
            with patch.object(manage, "CONFIG", config), self.assertRaises(RuntimeError):
                manage.config_install(False)
            self.assertEqual(config.read_text(), "operator owned\n")


class RuntimeRegistrationTests(unittest.TestCase):
    def test_host_python36_syntax_and_version_preflight(self):
        import ast
        ast.parse((HERE / "manage.py").read_text(), feature_version=(3, 6))
        with patch.object(manage.sys, "version_info", (3, 6, 8)), patch.object(manage.sys, "executable", "/usr/bin/python3"):
            manage.check_runtime()
        with patch.object(manage.sys, "version_info", (3, 5, 9)), self.assertRaises(RuntimeError):
            manage.check_runtime()
        with patch.object(manage.sys, "executable", "/usr/bin/env-python"), self.assertRaises(RuntimeError):
            manage.check_runtime()
        for version, accepted in (("1.18.0", False), ("1.19.3", True), ("1.24.0", True)):
            with patch.object(manage, "run", return_value=f"nginx version: nginx/{version}\n".encode()):
                if accepted:
                    manage.check_nginx()
                else:
                    with self.assertRaises(RuntimeError):
                        manage.check_nginx()
        with patch.object(manage, "run", return_value=b"Python 3.12.10\ncertbot 5.4.0\n") as run:
            manage.check_certbot()
        command = run.call_args.args
        self.assertIn("none", command)
        self.assertIn("/usr/local/bin/python", command)
        self.assertTrue(any("sys.version_info >= (3,10)" in item for item in command))
        self.assertFalse(any("type=bind" in item for item in command))
        self.assertIn("ExecStart=/usr/bin/python3 /usr/local/lib/crm-https/manage.py renew", (HERE / "crm-ip-renew.service").read_text())

    def test_without_email_is_explicit_in_both_environments(self):
        for environment in ("staging", "production"):
            with patch.object(manage, "check_certbot"), patch.object(manage, "prepare_acme"), patch.object(manage, "run") as run, patch.object(manage, "deploy_production"):
                manage.issue(environment, without_email=True)
            args = run.call_args.args
            self.assertIn("--register-unsafely-without-email", args)
            self.assertNotIn("--email", args)
        for email, without_email in ((None, False), ("ops@example.invalid", True), ("invalid", False)):
            with self.assertRaises(ValueError):
                manage.issue("staging", email, without_email)

    def test_cli_registration_mutual_exclusion_and_required_choice(self):
        for arguments in (("issue-staging",), ("issue-production", "--email", "ops@example.invalid", "--register-unsafely-without-email"), ("check", "--register-unsafely-without-email")):
            with patch.object(manage.sys, "argv", ["manage.py"] + list(arguments)), self.assertRaises(SystemExit):
                manage.main()
        for environment in ("staging", "production"):
            with patch.object(manage.sys, "argv", ["manage.py", "issue-" + environment, "--register-unsafely-without-email"]), patch.object(manage, "check_runtime"), patch.object(manage, "check_nginx"), patch.object(manage.os, "geteuid", return_value=0, create=True), patch.object(manage.os, "umask"), patch.object(manage, "issue") as issue:
                manage.main()
            issue.assert_called_once_with(environment, None, True)

    def test_renew_host_deploy_only_after_container_success(self):
        with patch.object(manage, "check_certbot"), patch.object(manage, "run", side_effect=RuntimeError("ACME failure")), patch.object(manage, "reload_nginx") as reload:
            with self.assertRaises(RuntimeError):
                manage.renew()
            reload.assert_not_called()
        events = []
        with patch.object(manage, "check_certbot"), patch.object(manage, "run", side_effect=lambda *_: events.append("container")), patch.object(manage, "certificate_check", side_effect=lambda: events.append("certificate")), patch.object(manage, "served_check", side_effect=RuntimeError("old leaf")), patch.object(manage, "reload_nginx", side_effect=lambda: events.append("reload")):
            manage.renew()
        self.assertEqual(events, ["container", "certificate", "reload"])


class ConfigTests(unittest.TestCase):
    def test_public_header_and_socket_boundary(self):
        tls = (HERE / "tls.conf").read_text()
        self.assertEqual(tls.count("proxy_pass http://127.0.0.1:8088;"), 2)
        for header in ("X-Forwarded-Proto https", "X-Forwarded-For $remote_addr", "X-Forwarded-Ssl ''", "X-Forwarded-Protocol ''", "Forwarded ''", "Host 8.133.190.46", "X-Frappe-Site-Name crm.localhost"):
            self.assertEqual(tls.count(f"proxy_set_header {header};"), 2, header)
        self.assertIn("if ($crm_socket_origin_ok = 0) { return 403; }", tls)
        self.assertIn("proxy_cookie_flags ~ secure;", tls)
        self.assertNotIn("staging", tls)
        self.assertIn("limit_req_status 429;", tls)
        http = (HERE / "http.conf").read_text()
        self.assertNotIn("proxy_pass", http)
        self.assertIn("return 308 https://8.133.190.46$request_uri;", http)

    def test_overlay_preserves_main_entrypoint_and_private_ports(self):
        overlay = (HERE / "compose.yml").read_text()
        self.assertNotIn("entrypoint:", overlay)
        self.assertNotIn("ports:", overlay)
        self.assertNotIn("db:", overlay)
        self.assertIn("prepare_inner.py:ro", overlay)
        self.assertIn("FORWARDED_ALLOW_IPS", overlay)

    def test_timer_hourly_persistent(self):
        timer = (HERE / "crm-ip-renew.timer").read_text()
        self.assertIn("OnCalendar=*-*-* *:17:00", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("manage.py renew", (HERE / "crm-ip-renew.service").read_text())


class StartupTests(unittest.TestCase):
    def test_launch_preserves_original_script_and_checks_before_exec(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            directory = Path(temporary)
            template = directory / "template"
            template.write_text(TEMPLATE)
            entrypoint = directory / "nginx-entrypoint.sh"
            original = "#!/bin/bash\nset -e\numask 0002\nexport BACKEND=backend:8000\ncat </templates/nginx/frappe.conf.template >/dev/null\nnginx -g 'daemon off;'\n"
            entrypoint.write_text(original)
            runtime = directory / "runtime"
            runtime.mkdir()
            with patch.object(inner.shutil, "which", return_value=str(entrypoint)), patch.object(inner.tempfile, "mkdtemp", return_value=str(runtime)), patch.object(inner.os, "execv") as execute:
                inner.launch(template)
            generated = (runtime / "nginx-entrypoint.sh").read_text()
            self.assertIn("export BACKEND=backend:8000", generated)
            self.assertIn("nginx -t\nexec nginx -g 'daemon off;'", generated)
            self.assertEqual((runtime / "frappe.conf.template").read_text(), inner.patch(TEMPLATE))
            self.assertEqual(entrypoint.read_text(), original)
            execute.assert_called_once()
            result = subprocess.run([inner.shutil.which("bash"), "-n", (runtime / "nginx-entrypoint.sh").as_posix()], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            entrypoint.write_text("unexpected start contract")
            with patch.object(inner.shutil, "which", return_value=str(entrypoint)), self.assertRaises(RuntimeError):
                inner.launch(template)

    def test_real_shell_overlay_default_and_security_rejections(self):
        trial = (HERE.parent / "remote" / "trial.sh").read_text()
        function = "compose() {" + trial.split("compose() {", 1)[1].split("\nverify_source()", 1)[0]
        with tempfile.TemporaryDirectory(dir=HERE) as temporary:
            directory = Path(temporary)
            overlay_dir = directory / "overlay"
            source = function.replace("/etc/crm-https", overlay_dir.as_posix())
            harness = '''fail() { printf '%s\\n' "$*" >&2; exit 1; }
stat() { if [ "$2" = '%u' ]; then printf '%s\\n' "${TEST_OWNER:-0}"; else printf '%s\\n' "${TEST_MODE:-755}"; fi; }
docker_cli() { printf '%s\\n' "$@"; }
PROJECT=fixture
ENV_FILE=credentials-placeholder
IMAGE_FILE=image-placeholder
REMOTE=base
'''
            def invoke(extra=""):
                return subprocess.run([inner.shutil.which("bash"), "-c", harness + extra + source + "\ncompose up"], capture_output=True, text=True)
            result = invoke()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("overlay/compose.yml", result.stdout)
            overlay_dir.mkdir()
            (overlay_dir / "compose.yml").write_text("services: {}")
            (overlay_dir / "prepare_inner.py").write_text("pass")
            result = invoke()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("overlay/compose.yml", result.stdout)
            for extra in ("TEST_MODE=777\n", "TEST_OWNER=1000\n"):
                result = invoke(extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("compose.yml\n", result.stdout)
            (overlay_dir / "prepare_inner.py").unlink()
            self.assertNotEqual(invoke().returncode, 0)


if __name__ == "__main__":
    unittest.main()
