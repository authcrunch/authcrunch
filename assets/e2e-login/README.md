# End-to-end login test

```sh
make e2e-login-test
```

The command builds the current checkout, starts its own HTTPS AuthCrunch process
on an available loopback port, creates a disposable user, and submits the actual
username and password forms for **John Smith (`jsmith`)** through Chromium. The
local identity store uses `path :memory:`; no user database is written to disk.
Desktop (1440 × 1000) and mobile
(390 × 844, touch emulation) run by default. No Docker daemon, external identity
provider, existing server, or supplied credentials are needed.

Prerequisites: macOS or Linux, the Go version required by `go.mod`, Python 3.11+
with `venv` and `pip`, Make, and Git. On first
use the command downloads pinned Python packages into `.tmp/e2e-login-tools/`
and the matching Playwright Chromium headless shell into Playwright's normal
browser cache. Subsequent runs reuse those tools. Dependencies are isolated
from the host Python installation. The first build needs access to Go modules.

On Linux, browser system libraries must also be available. To let Playwright
install its supported OS packages, run:

```sh
make e2e-login-test E2E_LOGIN_INSTALL_DEPS=1
```

This option can invoke `sudo` and `apt`; GitHub Actions enables it automatically.
Without it, the command does not install system packages.

## What it verifies

Each profile runs independent browser contexts for three cases:

1. An incorrect password gets HTTP 401, shows the rejection page, issues no
   access cookie, and cannot access the protected application.
2. An anonymous visitor follows the protected application's redirect, enters
   a username, completes the password challenge, and returns to the original
   application. The test checks Secure, HttpOnly and SameSite cookie flags;
   verifies the server's authenticated subject and role; reloads the application;
   opens a second tab; and signs out through the portal. Protected access must
   require login afterward, including from a fresh browser context.
3. A copy of the real issued JWT with a changed signature cannot access the
   protected application.

Uncaught JavaScript errors, HTTP 5xx responses, missing scripts/styles/fonts/images,
or attempted traffic outside the fixture fail the case. The runner uses bounded
navigation and assertion waits, makes no automatic test retries, and continues
to the remaining cases and profiles after an assertion failure. A failed,
interrupted, or unexecuted case never produces a passing run. Exit code zero
means every selected case completed successfully.

The fixture follows the upstream [on-demand TLS example](https://github.com/greenpau/caddy-security/blob/main/assets/config/auth.Caddyfile):

```caddyfile
on_demand_tls {
    ask http://localhost:5555/
}
```

An HTTP site at `http://localhost:5555`, bound to `127.0.0.1`, approves only
`domain=localhost` with HTTP 200 and rejects other or missing domains with HTTP
400. The HTTPS site uses `tls internal { on_demand }`. The runner verifies
Caddy's actual approval request during certificate issuance and both rejection
controls, recording `tls-checks.json`. It sets `skip_install_trust` so Caddy
does not change the host's trust store. Readiness verifies the generated CA;
browser contexts ignore its trust error. This test does not establish browser
certificate trust. Mobile coverage is Chromium emulation, not a physical device or Safari.
This suite covers local password authentication and browser cookie removal at
logout; it does not test MFA, federation, refresh flows, or server revocation of
copied JWTs.

## Report and diagnostics

The command prints the absolute path to `index.html` under a unique
`.tmp/e2e-login/<UTC timestamp>-<random suffix>/` directory. Open that file
directly in a browser. No report server or network connection is required.

The report includes:

- A screenshot timeline for each case, with profile/result/search filters and
  an enlarged viewer supporting arrow keys and Esc.
- Every assertion, observed values, step timings, and failure locations.
- Sanitized page source, network/console events, and full browser trace ZIPs.
- Redacted AuthCrunch debug/access logs, tool setup/build logs, and cleanup state.
- Commit/worktree information, the binary's SHA-256 and embedded Go build
  metadata, source file hashes, browser versions, and pinned tool requirements.
- `summary.json`, `junit.xml`, a GitHub-friendly `summary.md`, and `SHA256SUMS`.

To replay a trace, use the tool Python path shown in the report:

```sh
<tool-python> -m playwright show-trace <report-directory>/desktop/login-session-logout/trace.zip
```

The test creates only synthetic credentials. Text diagnostics redact the
generated password, signing key and JWTs; cookie diagnostics omit values.
**Trace ZIPs retain raw form bodies, DOM snapshots and disposable tokens** for
debugging. Treat the bundle as test evidence when sharing it. The CA/TLS private
keys, signing key, and runtime storage live outside the artifact
directory and are removed after the owned process stops. Identities stay in memory.
The normal Caddyfile,
user database, Go dependencies, and `bin/authcrunch` are not rewritten.

The runner records setup/build/startup failures as well as browser failures.
SIGINT/SIGTERM trigger cleanup of owned process groups and report finalization.
An uncatchable kill or machine loss cannot guarantee cleanup or final files;
the Actions finalizer reconstructs interrupted results from available evidence.

## Options

| Variable | Default | Purpose |
| --- | --- | --- |
| `E2E_LOGIN_PROFILES` | `desktop,mobile` | Run both profiles, or only `desktop` or `mobile`. |
| `E2E_LOGIN_OUTPUT` | A unique directory under `.tmp/e2e-login/` | Set an artifact destination; it must be empty or absent. |
| `E2E_LOGIN_BINARY` | Build current checkout | Test an existing executable; path is resolved from the checkout. Its hash and build metadata are recorded. |
| `E2E_LOGIN_INSTALL_DEPS` | Unset | Set to `1` to install Linux browser system libraries. |
| `E2E_LOGIN_ASK_PORT` | `5555` | Port for the loopback TLS approval endpoint. Use a different port for parallel runs, or `0` to allocate an available port. |

```sh
make e2e-login-test E2E_LOGIN_PROFILES=desktop
make e2e-login-test E2E_LOGIN_OUTPUT=.tmp/my-login-report
make e2e-login-test E2E_LOGIN_BINARY=bin/authcrunch
```

Report directories are never silently emptied or overwritten. Parallel runs
use distinct output/runtime directories and HTTPS ports; set
`E2E_LOGIN_ASK_PORT=0` to also allocate distinct approval ports. Tool installation
is locked. If the requested approval port is occupied, the run fails with a
report and leaves the existing listener alone.

## Run on demand in GitHub Actions

Open **Actions → E2E login test → Run workflow**, select a branch and profiles,
then run it. The workflow builds that checkout and invokes the same Make target.
It needs only read access to repository contents and no repository secrets.

Using the GitHub CLI:

```sh
gh workflow run e2e-login.yml --ref <branch> -f profiles=desktop,mobile
gh run list --workflow e2e-login.yml
gh run watch <run-id>
gh run download <run-id> --dir .tmp/downloaded-login-report
```

The job summary links to the artifact named
`authcrunch-e2e-login-<run-id>-<attempt>`. Download and extract the entire artifact,
then open `index.html`. Screenshots, logs, traces and machine-readable results
are uploaded on success and failure, with 14-day retention. A finalizer renders
an interrupted/setup-failure report when the test could not complete. Hard runner
loss can still prevent artifact upload. A report failure does not suppress the
test step's nonzero exit status.

Harness/report regression tests run offline through `make test-automation`.
They do not install a browser or build AuthCrunch.
