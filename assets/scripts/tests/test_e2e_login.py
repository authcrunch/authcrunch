"""Offline regression coverage for truthful reports and owned-process cleanup."""

from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import e2e_login as runner
import e2e_login_report as report


class LoginHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="authcrunch-harness-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.output = self.base / "report"
        self.output.mkdir()

    def write_results(self, records):
        directory = self.output / "desktop"
        directory.mkdir(exist_ok=True)
        runner.write_json(directory / "results.json", records)

    def completed_case(self):
        directory = self.output / "desktop/invalid-password"
        directory.mkdir(parents=True)
        (directory / "01.png").write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-test-fixture")
        (directory / "01.html.txt").write_text("<p>Recorded page</p>")
        (directory / "network.json").write_text('[{"kind":"response", "status":401}]')
        with zipfile.ZipFile(directory / "trace.zip", "w") as trace:
            trace.writestr("trace.trace", "{}")
        prefix = "desktop/invalid-password/"
        return {"id": "invalid-password", "profile": "desktop", "status": "passed",
                "checks": [{"description": "Rejected password", "passed": True}],
                "steps": [{"label": "Submit", "status": "passed", "screenshot": prefix + "01.png",
                           "source": prefix + "01.html.txt"}],
                "trace": prefix + "trace.zip", "events": prefix + "network.json"}

    def test_missing_and_interrupted_cases_never_count_as_passes(self):
        self.assertEqual([c["status"] for c in runner.collect_cases(self.output, ["desktop"])], ["not-run"] * 3)
        self.write_results([{"id": "invalid-password", "status": "running", "steps": [], "checks": []}])
        cases = runner.collect_cases(self.output, ["desktop"])
        self.assertEqual([c["status"] for c in cases], ["interrupted", "not-run", "not-run"])

    def test_duplicate_or_unknown_case_is_rejected(self):
        case = {"id": "invalid-password", "status": "running"}
        self.write_results([case, case])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            runner.collect_cases(self.output, ["desktop"])
        self.write_results([{"id": "invented-case"}])
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            runner.collect_cases(self.output, ["desktop"])

    def test_missing_capture_downgrades_claimed_success(self):
        case = self.completed_case()
        self.write_results([case])
        self.assertEqual(runner.collect_cases(self.output, ["desktop"])[0]["status"], "passed")
        (self.output / case["steps"][0]["screenshot"]).unlink()
        collected = runner.collect_cases(self.output, ["desktop"])[0]
        self.assertEqual(collected["status"], "failed")
        self.assertIn("Missing evidence", collected["error"])

    def test_failed_assertion_cannot_be_reported_as_a_pass(self):
        case = self.completed_case()
        case["checks"][0]["passed"] = False
        self.write_results([case])
        self.assertEqual(runner.collect_cases(self.output, ["desktop"])[0]["status"], "failed")

    def test_trace_must_be_a_real_archive(self):
        case = self.completed_case()
        (self.output / case["trace"]).write_text("not a trace")
        self.write_results([case])
        self.assertIn("not a ZIP", runner.collect_cases(self.output, ["desktop"])[0]["error"])

    def test_build_failure_still_writes_a_report_and_junit(self):
        with patch.object(runner, "prepare_tools", return_value=Path(sys.executable)), redirect_stdout(io.StringIO()):
            code = runner.execute(self.output, ["desktop"], str(self.base / "missing-binary"))
        self.assertEqual(code, 1)
        data = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(data["status"], "failed")
        self.assertEqual([c["status"] for c in data["cases"]], ["not-run"] * 3)
        self.assertIn("not executable", data["errors"][0])
        self.assertTrue((self.output / "index.html").is_file())
        suite = ET.parse(self.output / "junit.xml").getroot()
        self.assertEqual(suite.attrib["failures"], "1")
        self.assertEqual(suite.attrib["skipped"], "3")

    def test_occupied_approval_port_fails_without_touching_listener(self):
        binary = self.base / "candidate"
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o700)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with patch.dict(os.environ, E2E_LOGIN_ASK_PORT=str(port)), \
                    patch.object(runner, "prepare_tools", return_value=Path(sys.executable)), \
                    patch.object(runner, "metadata_command", return_value="test"), redirect_stdout(io.StringIO()):
                self.assertEqual(runner.execute(self.output, ["desktop"], str(binary)), 1)
            self.assertEqual(listener.getsockname()[1], port)
        data = json.loads((self.output / "summary.json").read_text())
        self.assertTrue(any("Address already in use" in error for error in data["errors"]))
        self.assertIsNone(data["server_exit_code"])

    def test_timeout_stops_owned_process(self):
        pid_file = self.base / "pid"
        script = f"import os,time; from pathlib import Path; Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(60)"
        with self.assertRaises(subprocess.TimeoutExpired):
            runner.command([sys.executable, "-c", script], self.output / "timeout.log", timeout=.5)
        pid = int(pid_file.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_sigterm_finalizes_a_failed_run(self):
        # Replace networked setup with a deterministic idle operation. Exercise
        # the real CLI signal handler, stage persistence and finalizer together.
        code = (f"import sys,time; from pathlib import Path; sys.path.insert(0,{str(SCRIPTS)!r}); "
                "import e2e_login as r; "
                "r.prepare_tools=lambda output: (print('setup-ready',flush=True),time.sleep(60))[1]; "
                f"sys.argv=['e2e_login.py','--output',{str(self.output)!r}]; sys.exit(r.main())")
        process = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(lambda: runner.stop(process))
        while "setup-ready" not in process.stdout.readline():
            self.assertIsNone(process.poll(), "Harness exited before entering setup")
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        self.assertNotEqual(process.returncode, 0, stdout + stderr)
        data = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(data["status"], "failed")
        self.assertTrue(any("Received signal" in error for error in data["errors"]))
        self.assertTrue((self.output / "index.html").is_file())

    def test_ci_finalizer_preserves_partial_evidence(self):
        self.write_results([{"id": "invalid-password", "status": "running", "steps": [], "checks": []}])
        runner.write_json(self.output / "summary.json", {"status": "running", "profiles": ["desktop"],
                          "stages": [{"name": "Browser", "status": "running"}], "errors": []})
        runner.finalize(self.output, "Workflow timed out")
        data = json.loads((self.output / "summary.json").read_text())
        self.assertEqual(data["status"], "interrupted")
        self.assertEqual(data["cases"][0]["status"], "interrupted")
        self.assertEqual(data["stages"][0]["status"], "interrupted")
        runner.finalize(self.output, "Must not duplicate errors")
        self.assertEqual(json.loads((self.output / "summary.json").read_text())["errors"], ["Workflow timed out"])

    def test_text_redaction_removes_password_signing_key_and_jwt(self):
        sample = 'password=unique-password key=unique-key jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqc21pdGgifQ.signature'
        redacted = runner.redact(sample, ["unique-password", "unique-key"])
        for secret in ("unique-password", "unique-key", "eyJhbGci"):
            self.assertNotIn(secret, redacted)


class LoginReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="authcrunch-report-test-")
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)

    def test_links_reject_traversal_external_urls_and_symlinks(self):
        (self.output / "evidence.txt").write_text("evidence")
        (self.output / "escape.txt").symlink_to(SCRIPTS / "e2e_login.py")
        for name in ("../evidence.txt", "/etc/passwd", "https://example.test/", "x\\y", "escape.txt"):
            self.assertIsNone(report.safe_path(self.output, name), name)
        self.assertEqual(report.safe_path(self.output, "evidence.txt"), "./evidence.txt")

    def test_report_escapes_diagnostic_html_and_uses_no_remote_assets(self):
        payload = '<img src=x onerror="alert(1)">'
        report.write_report(self.output, {"status": "failed", "errors": [payload], "cases": [], "stages": []})
        html = (self.output / "index.html").read_text()
        self.assertNotIn(payload, html)
        self.assertIn("&lt;img", html)
        self.assertIn("Content-Security-Policy", html)
        self.assertNotIn('<script src="https:', html)
        self.assertNotIn('<link href="https:', html)

    def test_junit_distinguishes_failure_skip_and_success(self):
        data = {"cases": [{"id": str(i), "profile": "desktop", "status": status}
                          for i, status in enumerate(("passed", "failed", "interrupted", "not-run"))],
                "errors": ["Tool setup failed"]}
        report.write_junit(self.output, data)
        suite = ET.parse(self.output / "junit.xml").getroot()
        self.assertEqual(suite.attrib["tests"], "5")
        self.assertEqual(suite.attrib["failures"], "3")
        self.assertEqual(suite.attrib["skipped"], "1")

    def test_sha256_inventory_covers_the_finished_report(self):
        (self.output / "debug data.txt").write_text("captured evidence")
        report.write_report(self.output, {"status": "passed", "cases": [], "stages": []})
        inventory = {}
        for line in (self.output / "SHA256SUMS").read_text().splitlines():
            checksum, name = line.split("  ", 1)
            inventory[name] = checksum
            self.assertEqual(checksum, hashlib.sha256((self.output / name).read_bytes()).hexdigest())
        self.assertIn("index.html", inventory)
        self.assertIn("junit.xml", inventory)
        self.assertIn("summary.md", inventory)
        self.assertIn("debug data.txt", inventory)
        self.assertNotIn("SHA256SUMS", inventory)


if __name__ == "__main__":
    unittest.main()
