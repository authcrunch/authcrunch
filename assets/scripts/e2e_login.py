#!/usr/bin/env python3
"""Own an isolated AuthCrunch process, browser tooling, and failure-safe report."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
import zipfile

from e2e_login_report import write_report

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "assets/e2e-login"
REQUIREMENTS = ROOT / "assets/scripts/e2e-login-requirements.txt"
PROFILES = ("desktop", "mobile")
SCENARIOS = ("invalid-password", "login-session-logout", "tampered-cookie")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stop(process):
    """Terminate only this run's process group, including browser descendants."""
    if process is None:
        return
    # Descendants can survive their direct parent's exit after an interruption.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def command(args, log, timeout=300, env=None, cwd=ROOT):
    with log.open("ab") as stream:
        stream.write(("$ " + " ".join(map(str, args)) + "\n").encode())
        stream.flush()
        process = subprocess.Popen(list(map(str, args)), cwd=cwd, env=env,
                                   stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            result = process.wait(timeout=timeout)
            if result:
                raise RuntimeError(f"{args[0]} exited {result}; see {log.name}")
        finally:
            stop(process)


def metadata_command(*args):
    result = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=15)
    return result.stdout.strip()


def redact(value, sensitive):
    for secret in sorted(filter(None, sensitive), key=len, reverse=True):
        value = value.replace(secret, "[REDACTED]")
    # Access tokens in structured server logs and captured markup.
    return re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED-JWT]", value)


@contextmanager
def tool_lock(path, timeout=600):
    with path.open("a") as stream:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out waiting for another browser-tool installation")
                time.sleep(.2)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def prepare_tools(output):
    cache = ROOT / ".tmp/e2e-login-tools"
    cache.mkdir(parents=True, exist_ok=True)
    # A new toolchain gets its own venv; parallel runs never replace a live one.
    fingerprint = hashlib.sha256(REQUIREMENTS.read_bytes() + sys.version.encode()).hexdigest()[:16]
    venv = cache / fingerprint
    python = venv / "bin/python"
    with tool_lock(cache / "install.lock"):
        if not (venv / ".ready").exists():
            command([sys.executable, "-m", "venv", venv], output / "setup.log")
            command([python, "-m", "pip", "install", "--disable-pip-version-check",
                     "-r", REQUIREMENTS], output / "setup.log")
            command([python, "-m", "pip", "check"], output / "setup.log")
            (venv / ".ready").touch()
        if os.environ.get("E2E_LOGIN_INSTALL_DEPS") == "1":
            # Opt-in only: Playwright may use sudo/apt on Linux. CI sets this.
            command([python, "-m", "playwright", "install-deps", "chromium"], output / "setup.log", timeout=600)
        # Playwright checks its matching browser revision and reuses cached files.
        command([python, "-m", "playwright", "install", "--only-shell", "chromium"],
                output / "setup.log")
    return python


def unused_port(requested=0):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", requested))
        return listener.getsockname()[1]


def wait_ready(server, origin, identity, certificate, timeout=30):
    # Verify the generated certificate for readiness, without changing host trust.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"AuthCrunch exited {server.returncode} before readiness; see server.log")
        try:
            if not certificate.exists():
                time.sleep(.1)
                continue
            context = ssl.create_default_context(cafile=str(certificate))
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                 urllib.request.HTTPSHandler(context=context))
            with opener.open(origin + "/healthz", timeout=1) as response:
                if response.status == 200 and response.read().decode() == identity:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.1)
    raise TimeoutError("AuthCrunch did not serve this run's health identity within 30 seconds")


def check_tls_approval(port, server_log):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    checks = []
    for query, expected in (("?domain=localhost", 200), ("?domain=untrusted.example.test", 400), ("", 400)):
        try:
            response = opener.open(f"http://localhost:{port}/" + query, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            checks.append({"query": query, "expected": expected, "observed": response.status})
            if response.status != expected:
                raise AssertionError(f"TLS ask endpoint returned {response.status}, expected {expected} for {query}")
    # The successful TLS handshake must have caused Caddy's own ask request.
    events = [json.loads(line) for line in server_log.read_text().splitlines() if line.startswith("{")]
    asks = [event for event in events if event.get("request", {}).get("uri") == "/?domain=localhost"]
    if len(asks) < 2:
        raise AssertionError("No evidence of the TLS issuer's ask request before the direct approval check")
    return checks


def collect_cases(output, profiles):
    cases = []
    for profile in profiles:
        path = output / profile / "results.json"
        records = json.loads(path.read_text()) if path.exists() else []
        if not isinstance(records, list) or len({c["id"] for c in records}) != len(records):
            raise ValueError(f"Invalid or duplicate case records for {profile}")
        if any(c["id"] not in SCENARIOS for c in records):
            raise ValueError(f"Unexpected case record for {profile}")
        for identifier in SCENARIOS:
            record = next((c for c in records if c["id"] == identifier), None)
            if record is None:
                record = {"id": identifier, "status": "not-run", "steps": [], "checks": []}
            if record.get("status") == "running":
                record["status"] = "interrupted"
            if record.get("status") == "passed":
                try:
                    validate_evidence(output, record)
                except (ValueError, OSError) as error:
                    record.update(status="failed", error=f"Incomplete passing evidence: {error}")
            record["profile"] = profile
            cases.append(record)
    return cases


def validate_evidence(output, record):
    """A success claim requires completed assertions and real captured evidence."""
    if not record.get("checks") or not all(c.get("passed") is True for c in record["checks"]):
        raise ValueError("Assertions are missing or include a failure")
    if not record.get("steps") or not all(s.get("status") == "passed" for s in record["steps"]):
        raise ValueError("Steps are missing or incomplete")

    def evidence_path(name):
        path = output / name
        if not path.resolve().is_relative_to(output.resolve()) or not path.is_file():
            raise ValueError(f"Missing evidence file: {name}")
        return path

    for step in record["steps"]:
        with evidence_path(step.get("screenshot", "")).open("rb") as stream:
            if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                raise ValueError("Screenshot is not a PNG")
        evidence_path(step.get("source", ""))
    if not zipfile.is_zipfile(evidence_path(record.get("trace", ""))):
        raise ValueError("Browser trace is not a ZIP")
    if not json.loads(evidence_path(record.get("events", "")).read_text()):
        raise ValueError("Browser events are empty")


class Run:
    def __init__(self, output, profiles):
        self.output = output
        self.data = {"schema_version": 1, "started_at": now(), "status": "running",
                     "profiles": profiles, "stages": [], "cases": [], "errors": [],
                     "fixture": {"name": "John Smith", "username": "jsmith", "identity_store": ":memory:"},
                     "environment": {"os": platform.platform(), "python": sys.version.split()[0]},
                     "tls_note": "Caddy issues an internal certificate on demand after approval by the loopback ask endpoint. Readiness validates the generated CA; browser contexts ignore its trust error. Host certificate trust is unchanged."}
        self.save()

    def save(self):
        write_json(self.output / "summary.json", self.data)

    @contextmanager
    def stage(self, name):
        print(f"e2e-login-test: {name}", flush=True)
        stage = {"name": name, "status": "running", "started_at": now()}
        self.data["stages"].append(stage)
        self.save()
        started = time.monotonic()
        try:
            yield
        except BaseException as error:
            stage.update(status="failed", error=str(error))
            raise
        else:
            stage["status"] = "passed"
        finally:
            stage.update(duration_ms=round((time.monotonic() - started) * 1000), finished_at=now())
            self.save()


def execute(output, profiles, supplied_binary):
    run = Run(output, profiles)
    server = None
    password, signing_key = "E2e!" + secrets.token_urlsafe(24), secrets.token_hex(32)
    sensitive = [password, signing_key]
    # Keep keys and user DB outside the upload directory. Always destroy them.
    with tempfile.TemporaryDirectory(prefix="authcrunch-login-") as temporary:
        runtime = Path(temporary)
        try:
            with run.stage("Prepare pinned browser tools"):
                if sys.version_info < (3, 11):
                    raise RuntimeError("Python 3.11 or newer is required")
                python = prepare_tools(output)
                run.data["environment"].update(tool_python=str(python), requirements_sha256=digest(REQUIREMENTS))
                shutil.copyfile(REQUIREMENTS, output / "requirements.txt")
            with run.stage("Build AuthCrunch candidate"):
                binary = Path(supplied_binary).expanduser().resolve() if supplied_binary else runtime / "authcrunch"
                if not supplied_binary:
                    environment = dict(os.environ, GOPROXY=os.environ.get("GOPROXY", "https://proxy.golang.org,direct"))
                    command(["go", "build", "-mod=readonly", "-o", binary, "."], output / "build.log",
                            timeout=600, env=environment)
                if not binary.is_file() or not os.access(binary, os.X_OK):
                    raise RuntimeError(f"AuthCrunch binary is not executable: {binary}")
                run.data["candidate"] = {"binary_sha256": digest(binary), "supplied_binary": bool(supplied_binary),
                                         "commit": metadata_command("git", "rev-parse", "HEAD"),
                                         "worktree": metadata_command("git", "status", "--short"),
                                         "go": metadata_command("go", "version")}
                (output / "binary-build-info.txt").write_text(metadata_command("go", "version", "-m", str(binary)) + "\n")
                source_files = ["main.go", "go.mod", "go.sum", "Makefile"]
                source_files += [str(p.relative_to(ROOT)) for p in FIXTURES.glob("*")]
                source_files += [str(p.relative_to(ROOT)) for p in (ROOT / "assets/scripts").glob("e2e*.*")]
                write_json(output / "source-manifest.json", {p: digest(ROOT / p) for p in sorted(source_files)})
            with run.stage("Start isolated HTTPS instance"):
                ask_port = unused_port(int(os.environ.get("E2E_LOGIN_ASK_PORT") or "5555"))
                host = f"localhost:{unused_port()}"
                origin = "https://" + host
                health = secrets.token_hex(16)
                environment = dict(os.environ, E2E_LOGIN_RUNTIME=str(runtime), E2E_LOGIN_PASSWORD=password,
                                   E2E_LOGIN_SIGNING_KEY=signing_key, E2E_LOGIN_ORIGIN=origin,
                                   E2E_LOGIN_HOST=host, E2E_LOGIN_ASK_PORT=str(ask_port),
                                   E2E_LOGIN_FIXTURES=str(FIXTURES), E2E_LOGIN_HEALTH=health,
                                   XDG_DATA_HOME=str(runtime / "data"), XDG_CONFIG_HOME=str(runtime / "config"))
                shutil.copyfile(FIXTURES / "Caddyfile", output / "Caddyfile")
                with (runtime / "server.log").open("wb") as log:
                    server = subprocess.Popen([str(binary), "run", "--config", str(FIXTURES / "Caddyfile"),
                                               "--adapter", "caddyfile"], cwd=runtime, env=environment,
                                              stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                certificate = runtime / "storage/pki/authorities/local/root.crt"
                wait_ready(server, origin, health, certificate)
                shutil.copyfile(certificate, output / "root.crt")
                run.data["origin"] = origin
                run.data["ask_url"] = f"http://localhost:{ask_port}/"
            with run.stage("Verify on-demand TLS approval and rejection"):
                run.data["tls_checks"] = check_tls_approval(ask_port, runtime / "server.log")
                write_json(output / "tls-checks.json", run.data["tls_checks"])
            # Each profile continues independently after a browser assertion fails.
            for profile in profiles:
                try:
                    with run.stage(f"Exercise {profile} browser"):
                        command([python, ROOT / "assets/scripts/e2e_login_browser.py", "--output", output,
                                 "--origin", origin, "--profile", profile], output / f"{profile}-runner.log",
                                timeout=240, env=environment)
                except (RuntimeError, subprocess.TimeoutExpired) as error:
                    run.data["errors"].append(str(error))
            if server.poll() is not None:
                raise RuntimeError(f"AuthCrunch exited unexpectedly: {server.returncode}")
        except (Exception, KeyboardInterrupt) as error:
            run.data["errors"].append(f"{type(error).__name__}: {error}")
            (output / "harness-error.txt").write_text(redact(traceback.format_exc(), sensitive))
        finally:
            with run.stage("Stop owned instance and collect diagnostics"):
                stop(server)
                run.data["server_exit_code"] = server.returncode if server else None
                if (runtime / "server.log").exists():
                    (output / "server.log").write_text(redact((runtime / "server.log").read_text(errors="replace"), sensitive))
                # Trace ZIPs intentionally retain raw disposable browser evidence.
                for path in output.rglob("*"):
                    if path.suffix in (".log", ".txt", ".json"):
                        path.write_text(redact(path.read_text(errors="replace"), sensitive))
    try:
        run.data["cases"] = collect_cases(output, profiles)
    except (ValueError, KeyError, TypeError) as error:
        run.data["errors"].append(f"Invalid browser evidence: {error}")
    run.data["finished_at"] = now()
    passed = (not run.data["errors"] and len(run.data["cases"]) == len(profiles) * len(SCENARIOS)
              and all(c["status"] == "passed" for c in run.data["cases"]))
    run.data["status"] = "passed" if passed else "failed"
    run.save()
    write_report(output, run.data)
    return 0 if passed else 1


def finalize(output, reason, profiles=PROFILES):
    """CI fallback when setup, cancellation or an outer timeout prevented finalization."""
    output.mkdir(parents=True, exist_ok=True)
    summary = output / "summary.json"
    data = json.loads(summary.read_text()) if summary.exists() else {
        "schema_version": 1, "started_at": now(), "profiles": list(profiles), "stages": [], "errors": []}
    if data.get("status") not in ("passed", "failed", "interrupted"):
        data.update(status="interrupted", finished_at=now())
        data["errors"].append(reason)
        for stage in data["stages"]:
            if stage["status"] == "running":
                stage["status"] = "interrupted"
        data["cases"] = collect_cases(output, data["profiles"])
        write_json(summary, data)
    write_report(output, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=os.environ.get("E2E_LOGIN_OUTPUT") or "")
    parser.add_argument("--profiles", default=os.environ.get("E2E_LOGIN_PROFILES") or ",".join(PROFILES))
    parser.add_argument("--binary", default=os.environ.get("E2E_LOGIN_BINARY") or "")
    parser.add_argument("--finalize", action="store_true", help="Render an interrupted CI run without launching processes")
    parser.add_argument("--reason", default="Workflow setup failed or the test was interrupted before completion.")
    args = parser.parse_args()
    profiles = args.profiles.split(",")
    if not profiles or len(set(profiles)) != len(profiles) or any(p not in PROFILES for p in profiles):
        parser.error("profiles must be desktop, mobile, or desktop,mobile")
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(3)
    output = Path(args.output).expanduser().resolve() if args.output else ROOT / ".tmp/e2e-login" / name
    os.umask(0o077)
    if args.finalize:
        if not args.output:
            parser.error("--finalize requires --output")
        finalize(output, args.reason, profiles)
        return 0
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be empty; previous evidence is never overwritten")
    output.mkdir(parents=True, exist_ok=True)

    def interrupted(number, _frame):
        raise InterruptedError(f"Received signal {number}")

    for number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(number, interrupted)
    print(f"e2e-login-test: report directory {output}", flush=True)
    try:
        result = execute(output, profiles, args.binary)
    finally:
        # Also covers unexpected collection/cleanup errors; never turn them green.
        finalize(output, "Harness stopped before completing its report.")
    print(f"e2e-login-test: {'PASS' if result == 0 else 'FAIL'} · {output / 'index.html'}", flush=True)
    return result


if __name__ == "__main__":
    sys.exit(main())
