# AuthCrunch threat model for OSS Scanner

## Project and assessment focus

The enrollment target is [authcrunch/authcrunch](https://github.com/authcrunch/authcrunch),
a distribution of a Caddy-based authentication portal and authorization gateway.
Its top-level Go program mostly registers modules and starts Caddy. Reviewing
only this small wrapper would miss the implementation of its security controls.

**Focus the assessment on `caddy-security` and the `go-authcrunch` library that
serves as its foundation**, following attacker-controlled inputs from this
distribution into those components:

| Component | Role and review priorities |
| --- | --- |
| [greenpau/caddy-security](https://github.com/greenpau/caddy-security) | Caddy `security` application; `authenticate` and `authorize` handlers; Caddyfile-to-runtime configuration; middleware ordering, request identity, policy selection, provisioning, reload, and optional backend integration. |
| [greenpau/go-authcrunch](https://github.com/greenpau/go-authcrunch) | Core authentication and authorization; local/LDAP identities; OAuth/OIDC/SAML; passwords, MFA and recovery; JWT/PASETO and key handling; session and refresh lifecycles; registration, administration, embedded portal UI, and storage/plugin contracts. |
| This repository | Selection and combination of modules in `main.go`, dependency pins, container contents, and configuration or packaging decisions that expose or weaken those controls. |

These are maintained parts of the AuthCrunch project, not unrelated targets.
Use the versions selected by the checked-out `go.mod` and `go.sum`. The audit
image preserves their source and test dependencies, so the review can follow
the full implementation offline. Do not substitute their latest development
branches and then attribute a defect to a different version in this distribution.

This is one enrollment for `authcrunch/authcrunch`. Findings rooted in a
foundation library should establish how the affected behavior is reachable
through this distribution, identify the owning upstream component, and include
the relevant dependency version. This does not authorize scanning unrelated
dependencies, hosted services, or other repositories as independent targets.

## Assets and trust boundaries

Protect account credentials, MFA material, private signing keys, API keys,
session and refresh credentials, identity/role assignments, protected upstream
resources, registration and administrative operations, and private user data.

Assume an unauthenticated Internet client can send arbitrary HTTP requests to
the portal and protected application routes. An attacker may also have a
legitimate account with limited roles or control a browser and its cookies,
headers, query parameters, form/API bodies, uploaded data, and concurrent
requests. Another tenant or realm's authenticated identity is not authority
over the victim's tenant, realm, account, or resource.

Distinguish these boundaries:

- Network requests enter Caddy routing and authentication/authorization
  middleware before reaching a protected resource. Client-controlled forwarding
  headers are not trusted unless an explicit proxy configuration establishes
  that trust. Host, origin, path and redirect handling must preserve this boundary.
- Authentication establishes a specific identity and its authentication strength;
  authorization separately grants access to a specific resource. A valid token
  is insufficient if its issuer, audience, realm, role, session or resource
  binding does not satisfy the configured policy.
- External identity providers, LDAP servers, JWKS endpoints, secret managers,
  policy services and backend stores have explicitly configured authority.
  Validate protocol messages, signatures, bindings and parsing even when the peer
  is configured; do not grant a peer authority beyond its configured purpose.
- Operators control Caddy configuration, environment secrets, backend credentials
  and protected key files. Ordinary remote users do not. Caddy's administrative
  API and management credentials are privileged interfaces, not public login APIs.

Features such as OIDC provider mode, refresh tokens, external authorization,
registration and optional storage plugins require configuration. Findings in
them remain relevant when demonstrated with a supported configuration; include
that configuration and its prerequisites rather than claiming universal exposure.

## Highest-value attack surfaces

1. **Authentication bypass or identity confusion.** Password, Basic and API-key
   verification; MFA enrollment/challenges/recovery; cross-device and federated
   login; provider/account linking; sandbox/challenge binding; transitions from
   partially authenticated state to a fully authorized session.
2. **Authorization bypass and privilege escalation.** ACL/role evaluation,
   tenant/realm separation, path normalization, bypass and fallback rules,
   middleware delegation, claims transforms, required external decisions,
   administrative operations and user-controlled object identifiers.
3. **Token and protocol integrity.** Signature/algorithm/key selection, issuer
   and audience validation, token source precedence, JWKS trust, OAuth state,
   nonce, PKCE, redirect URI validation, authorization code replay, SAML signature
   and recipient validation, and confusion between protocol-specific token types.
4. **Session integrity.** Cookie scope and attributes, login/logout behavior,
   session fixation, refresh rotation/reuse/revocation, expiry, concurrent state
   changes, reload/restart behavior, and persistence/namespace isolation.
5. **Injection, confidentiality and availability.** Stored/reflected XSS in the
   portal; CSRF on sensitive actions; SQL/LDAP/template/command injection; SSRF
   involving attacker-influenced destinations; path traversal or file disclosure;
   leaking credentials in errors/logs/headers; and remotely triggerable resource
   exhaustion, panics or races with a practical service impact.

Assess optional modules actually compiled into `main.go` and the production
Dockerfile, including SQLite/Consul backends, external authorization and secrets
integrations, where their configuration makes an attack path reachable. An
imported module is not necessarily enabled for every deployment.

## Exercising the project offline

The scanner builds `.oss-scanner/Dockerfile` with this repository as its context.
The resulting image provides:

- `/src`: this checkout, including the login fixture and automation tests.
- `/opt/oss-scanner/bin/authcrunch`: the binary built from this checkout.
- `/opt/oss-scanner/foundation/caddy-security` and
  `/opt/oss-scanner/foundation/go-authcrunch`: writable copies of the exact
  selected foundation modules, with their tests and module dependencies prepared.
- `/opt/oss-scanner/build-info.txt` and `/opt/oss-scanner/modules.json`:
  build provenance and the selected dependency graph.
- The Go toolchain/module/build caches and the pinned Playwright browser/tool
  environment used by `make e2e-login-test`. `GOPROXY=off` prevents downloads
  during assessment; Go checksum verification has not been disabled.

From `/src`, useful starting points are:

```sh
go test -mod=readonly ./...
go build -mod=readonly -o /tmp/authcrunch-audit .
make test-automation
make e2e-login-test E2E_LOGIN_ASK_PORT=0
```

The wrapper has little Go code and currently no Go unit tests of its own; its
successful `go test ./...` result does not establish library coverage. The
browser journey exercises a real local portal and protected resource with the
in-memory user John Smith (`jsmith`), a generated password, and on-demand internal
TLS. Its generated screenshots, traces and diagnostics are under `.tmp/e2e-login/`.
The fixture does not establish browser certificate trust or prove server-side
revocation of a copied stateless JWT after logout.

Read each foundation component's tests and fixtures in the prepared source
copies. Their tests are compiled during setup; long-running, race-enabled and
browser integration suites can be selected as needed. Use bounded execution
and limited package parallelism. Prefer a focused regression or reproducer over
running every integration journey. If modifying foundation code to demonstrate
a fix, explicitly bind the modified source into a temporary module/workspace
before rebuilding `/src`; editing a copy alone does not change the linked binary.

The audit image builds the Go-module distribution. The production Dockerfile
also selects Docker-only modules and resolves `authdbctl@latest`; inspect its
actual build versions before asserting that an audit binary and a published
container have identical contents. Builds, tests and reproductions must use
synthetic credentials, local mock providers/backends, and loopback listeners.

## Severity and reporting

Rate severity by the demonstrated impact and prerequisites, not by a weakness
label alone. Unauthenticated code execution, broad authentication bypass or
administrative takeover can be critical. Cross-account privilege escalation,
usable credential/token theft or a protocol bypass with substantial account
impact will generally be high. Limited-scope compromise, practical denial of
service or attacks with meaningful prerequisites may be medium; defense-in-depth
improvements without a demonstrated boundary violation are generally low.
State the affected deployment and explain any rating that depends on scale,
trusted-operator actions, unusual configuration or prior account access.

Send findings privately to **greenpau@outlook.com**, as also documented in
`SECURITY.md`. Include:

- Affected component, version, source locations and reachable entry point.
- Attacker capabilities, required configuration and the violated boundary.
- A minimal local reproducer with exact commands, expected versus observed
  behavior, and evidence of impact; clearly label hypotheses that are unverified.
- A proposed regression test and narrowly scoped remediation when available.
  Place library fixes in the component that owns the behavior and explain how
  this distribution would consume them.

Deduplicate by root cause across the wrapper, adapter, library and protocol
variants. Do not publish exploit details, send real credentials, or probe live
deployments as part of this assessment.

## Scope limits and expected behavior

Operator-chosen insecure configurations, possession of a signing key or
administrative credential, deliberate authorization bypass rules, and a trusted
administrator intentionally assigning privileged roles are not independently
authentication bypasses. A defect that exceeds that configured authority is in
scope. Likewise, a malicious configured provider is not by itself a finding;
show a broken validation or authority boundary.

Examples, test keys, generated test accounts and disposable browser traces are
not production secrets. The standalone `authdb` server or an uncompiled plugin
is useful context but needs an explicit distribution-reachable impact for this
enrollment. Third-party dependency findings without an AuthCrunch-specific
integration or reachable exploit path should not be submitted as findings in
this project.
