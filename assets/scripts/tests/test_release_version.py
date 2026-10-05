"""Exercise release metadata and Git operations using temporary local repositories."""

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path("assets/scripts/release_version.sh")


class ReleaseVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="authcrunch-release-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.env = os.environ.copy()
        for name in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "RELEASE_TAG"):
            self.env.pop(name, None)
        (self.repo / SCRIPT).parent.mkdir(parents=True)
        shutil.copyfile(ROOT / SCRIPT, self.repo / SCRIPT)
        shutil.copyfile(ROOT / "Makefile", self.repo / "Makefile")
        self.write("go.mod", "module example.com/authcrunch\n\nrequire (\n"
                   "\tgithub.com/caddyserver/caddy/v2 v2.11.7\n"
                   "\tgithub.com/greenpau/caddy-security v1.4.1\n)\n")
        self.write("VERSION", "1.0.47\n")
        self.write("Dockerfile", "FROM caddy:2.11.7-builder AS builder\n"
                   "RUN xcaddy build \\\n"
                   "    --with github.com/greenpau/caddy-security@v1.4.1\n"
                   "FROM caddy:2.11.7\n"
                   "LABEL org.opencontainers.image.version=1.3.11\n")

    def write(self, name, contents):
        (self.repo / name).write_text(contents)

    def read(self, name):
        return (self.repo / name).read_text()

    def run_cmd(self, *args, success=True):
        result = subprocess.run(args, cwd=self.repo, env=self.env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def script(self, *args, success=True):
        return self.run_cmd("bash", str(SCRIPT), *args, success=success)

    def init_git(self):
        self.run_cmd("git", "init", "-b", "main")
        for key, value in (("user.name", "Release Test"),
                           ("user.email", "release-test@example.com"),
                           ("commit.gpgsign", "false"), ("tag.gpgSign", "false"),
                           ("core.hooksPath", "/dev/null")):
            self.run_cmd("git", "config", key, value)
        self.run_cmd("git", "add", ".")
        self.run_cmd("git", "commit", "-m", "test: initial state")

    def init_release(self, synced=False):
        if synced:
            self.script("sync")
        self.init_git()
        self.remote = self.base / "origin.git"
        self.run_cmd("git", "init", "--bare", str(self.remote))
        self.run_cmd("git", "remote", "add", "origin", str(self.remote))
        self.run_cmd("git", "push", "-u", "origin", "main")
        # Release tests execute real Git against a local bare repository only.
        # Go module verification is stubbed to avoid network access.
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        go = bin_dir / "go"
        go.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$GO_TEST_LOG"\n')
        go.chmod(0o755)
        self.env["PATH"] = str(bin_dir) + os.pathsep + self.env["PATH"]
        self.env["GO_TEST_LOG"] = str(self.base / "go.log")

    def test_sync_and_check_match_plugin(self):
        original_mod = self.read("go.mod")
        self.script("sync")
        self.assertEqual(self.read("VERSION"), "1.4.1\n")
        self.assertIn("LABEL org.opencontainers.image.version=1.4.1\n",
                      self.read("Dockerfile"))
        self.assertEqual(self.read("go.mod"), original_mod)
        self.script("check", "v1.4.1")
        synced_docker = self.read("Dockerfile")
        self.script("sync")
        self.assertEqual(self.read("Dockerfile"), synced_docker)

    def test_check_rejects_stale_metadata_and_wrong_tag(self):
        self.assertIn("VERSION must be 1.4.1", self.script("check", success=False))
        self.write("VERSION", "1.4.1\n")
        self.assertIn("Docker image version must be 1.4.1",
                      self.script("check", success=False))
        self.script("sync")
        self.assertIn("must be 'v1.4.1'",
                      self.script("check", "v1.0.48", success=False))

    def test_sync_rejects_invalid_or_missing_plugin_without_writes(self):
        original_mod = self.read("go.mod")
        original_docker = self.read("Dockerfile")
        for pin in ("", "main", "v1.4", "v01.4.1"):
            with self.subTest(pin=pin):
                self.write("go.mod", original_mod.replace("v1.4.1", pin))
                self.script("sync", success=False)
                self.assertEqual(self.read("VERSION"), "1.0.47\n")
                self.assertEqual(self.read("Dockerfile"), original_docker)

    def test_sync_rejects_different_docker_plugin(self):
        self.write("Dockerfile", self.read("Dockerfile").replace("@v1.4.1", "@v1.3.0"))
        self.assertIn("Dockerfile pins 'v1.3.0'", self.script("sync", success=False))
        self.assertEqual(self.read("VERSION"), "1.0.47\n")

    def test_sync_rejects_missing_or_duplicate_label(self):
        original = self.read("Dockerfile")
        label = "LABEL org.opencontainers.image.version=1.3.11\n"
        for dockerfile in (original.replace(label, ""), original + label):
            with self.subTest(dockerfile=dockerfile):
                self.write("Dockerfile", dockerfile)
                self.script("sync", success=False)
                self.assertEqual(self.read("Dockerfile"), dockerfile)
                self.assertEqual(self.read("VERSION"), "1.0.47\n")

    def test_single_line_requirement_and_prerelease(self):
        self.write("go.mod", "module example.com/authcrunch\n"
                   "require github.com/greenpau/caddy-security v1.5.0-rc.1\n")
        self.write("Dockerfile", self.read("Dockerfile").replace("v1.4.1", "v1.5.0-rc.1"))
        self.script("sync")
        self.script("check", "v1.5.0-rc.1")
        self.assertEqual(self.read("VERSION"), "1.5.0-rc.1\n")

    def test_sync_versions_updates_release_metadata(self):
        self.write("go.mod", self.read("go.mod").replace("v1.4.1", "v1.4.2-rc.1"))
        self.write("Dockerfile", self.read("Dockerfile").replace("v1.4.1", "v1.4.2-rc.1"))
        self.init_git()
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        git = bin_dir / "git"
        real_git = shlex.quote(shutil.which("git"))
        git.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = "-c" ] && [ "$3" = "ls-remote" ]; then\n'
            '  case "$8" in\n'
            '    */caddy-security) version=v1.4.2 ;;\n'
            '    */caddy-trace) version=v1.1.13 ;;\n'
            '    */caddy-security-secrets-aws-secrets-manager) version=v1.0.1 ;;\n'
            '    */caddy) version=v2.11.8 ;;\n'
            '    *) exit 1 ;;\n'
            '  esac\n'
            '  printf "0123456789\\trefs/tags/%s\\n" "$version"\n'
            '  exit 0\n'
            'fi\n'
            f'exec {real_git} "$@"\n')
        git.chmod(0o755)
        self.env["PATH"] = str(bin_dir) + os.pathsep + self.env["PATH"]
        self.run_cmd("make", "sync-versions")
        self.run_cmd("make", "check-release-version", "RELEASE_TAG=v1.4.2")
        self.assertEqual(self.read("VERSION"), "1.4.2\n")
        self.assertIn("FROM caddy:2.11.8-builder", self.read("Dockerfile"))

    def test_release_tags_synced_commit_without_changing_version(self):
        self.init_release(synced=True)
        before = self.run_cmd("git", "rev-parse", "HEAD")
        # An unrelated local tag must not be published along with the release.
        self.run_cmd("git", "tag", "unrelated-test-tag")
        self.run_cmd("make", "release")
        self.script("check", "v1.4.1")
        self.assertEqual(self.run_cmd("git", "rev-parse", "HEAD"), before)
        self.assertEqual(self.run_cmd("git", "rev-parse", "v1.4.1^{commit}"), before)
        self.assertEqual(self.run_cmd("git", "cat-file", "-t", "v1.4.1").strip(), "tag")
        remote_tags = self.run_cmd("git", "ls-remote", "--tags", "origin")
        self.assertIn("refs/tags/v1.4.1", remote_tags)
        self.assertNotIn("unrelated-test-tag", remote_tags)
        self.assertEqual(self.run_cmd("git", "status", "--porcelain"), "")
        self.assertEqual(Path(self.env["GO_TEST_LOG"]).read_text(), "mod tidy\nmod verify\n")

    def test_release_rejects_stale_metadata_without_changing_it(self):
        self.init_release()
        self.assertIn("VERSION must be 1.4.1", self.run_cmd("make", "release", success=False))
        self.assertEqual(self.read("VERSION"), "1.0.47\n")
        self.assertEqual(self.run_cmd("git", "status", "--porcelain"), "")
        self.assertEqual(self.run_cmd("git", "tag", "--list"), "")

    def test_release_rejects_existing_local_tag_before_writes(self):
        self.init_release(synced=True)
        self.run_cmd("git", "tag", "v1.4.1")
        before = self.run_cmd("git", "rev-parse", "HEAD")
        self.assertIn("already exists locally", self.run_cmd("make", "release", success=False))
        self.assertEqual(self.read("VERSION"), "1.4.1\n")
        self.assertEqual(self.run_cmd("git", "rev-parse", "HEAD"), before)

    def test_release_rejects_existing_remote_tag_before_writes(self):
        self.init_release(synced=True)
        self.run_cmd("git", "push", "origin", "HEAD:refs/tags/v1.4.1")
        self.assertIn("already exists on origin", self.run_cmd("make", "release", success=False))
        self.assertEqual(self.read("VERSION"), "1.4.1\n")
        self.assertEqual(self.run_cmd("git", "tag", "--list"), "")

    def test_release_rejects_non_main_branch_and_dirty_tree(self):
        self.init_release()
        self.run_cmd("git", "switch", "-c", "feature")
        self.assertIn("cannot release to non-main branch",
                      self.run_cmd("make", "release", success=False))
        self.run_cmd("git", "switch", "main")
        self.write("VERSION", "1.0.48\n")
        self.assertIn("git directory is dirty", self.run_cmd("make", "release", success=False))
        self.assertEqual(self.run_cmd("git", "tag", "--list"), "")


if __name__ == "__main__":
    unittest.main()
