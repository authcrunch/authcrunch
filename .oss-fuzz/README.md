# OSS-Fuzz integration

Enrollment is proposed in [google/oss-fuzz#16362](https://github.com/google/oss-fuzz/pull/16362).
OSS-Fuzz service activation requires upstream acceptance and deployment.

AuthCrunch's enrollment targets the Caddy Security adapter and the underlying
go-authcrunch authentication and authorization library. The integration lives in
[`projects/authcrunch` in OSS-Fuzz](https://github.com/google/oss-fuzz/tree/master/projects/authcrunch).
The primary engineering contact is `greenpau.git@gmail.com`.

The build uses the exact foundation versions selected by this repository's
`go.mod`, verifies downloaded modules, and compiles their native Go fuzz targets
with OSS-Fuzz's `compile_native_go_fuzzer_v2`. Writable source copies and local
module replacements are created only inside the disposable build container.
Upstream development branches and local sibling checkouts are not substituted.

The initial targets exercise Caddyfile OAuth directive encoding, path ACLs,
JWT authorization, OIDC authorization parameters, OIDC request objects and
loopback redirects, Argon2 password-hash parsing, and OAuth JWKS validation.
They retain the foundation libraries' security assertions. Explicit seed corpora
are converted with OSS-Fuzz's converter because the adapter ignores `F.Add`.

To validate locally with Docker and Python 3, clone OSS-Fuzz and run from that
checkout (replace `/path/to/authcrunch` with this repository's absolute path):

```sh
python3 -m pip install PyYAML==6.0.2 requests==2.31.0
python3 infra/helper.py build_image --pull authcrunch
python3 infra/helper.py build_fuzzers --sanitizer address authcrunch /path/to/authcrunch
python3 infra/helper.py check_build --sanitizer address authcrunch
python3 infra/helper.py build_fuzzers --sanitizer coverage authcrunch /path/to/authcrunch
```

The source mount is writable: use a disposable checkout because the native Go
adapter and build preparation modify module metadata and source during conversion.
Do not point the source mount at your working checkout with uncommitted changes.

The **OSS-Fuzz integration** GitHub Actions workflow runs these builds on demand,
exercises all address targets and their seed corpora, and uploads logs. Native Go
coverage binaries are test executables, so the workflow validates their
compilation, matching OSS-Fuzz's upstream CI. Its repository/ref inputs allow
testing an enrollment branch before it merges into OSS-Fuzz. After acceptance,
use the defaults `google/oss-fuzz` and `master`. OSS-Fuzz then supplies continuous
fuzzing; the manual workflow is bounded validation, not a replacement for it.

While enrollment is pending, validate the proposal with:

```sh
gh workflow run oss-fuzz.yml --repo authcrunch/authcrunch \
  -f integration_repository=greenpau/oss-fuzz -f integration_ref=enroll-authcrunch
```

When updating foundation versions, run both build modes. A renamed or removed
fuzz function must be updated in OSS-Fuzz's `fuzzers.json`; the build fails if a
declared target does not produce a binary. Investigate findings in the component
that owns the behavior, add an upstream regression, and update the distribution
to consume the fix. Caddy itself has a separate OSS-Fuzz enrollment; these targets
focus on AuthCrunch's authentication-specific implementation.
