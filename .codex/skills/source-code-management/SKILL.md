---
name: source-code-management
description: authcrunch source code management and commit message rules. Use when creating, reviewing, or updating commit messages, especially when the user asks to create a commit message for a change in this repository.
---

# Source Code Management

## Commit Message Rules

All hand-written commits must have a proper commit message.

A hand-written commit message subject line must conform to these rules:

- The first line of each commit message is the subject.
- The subject line MUST be less than 87 characters long.
- The subject line MUST NOT terminate with a period (`.`).
- The subject line MUST start with a change indicator followed by a colon
  (`:`).

## Change Indicators

Use exactly one indicator. Prefer the most specific repository surface when the
change is clearly anchored there. Use a maintenance label when the change is
repository plumbing, documentation, tests, release work, or cross-cutting
maintenance.

Use one of these indicators:

- `build`: local binary build behavior, build flags, or `bin/authcrunch`
  generation
- `caddy`: Caddy runtime integration, Caddy module wiring, `main.go`, or
  Caddyfile behavior
- `deps`: dependency updates in `go.mod` or `go.sum`
- `docker`: Dockerfile image contents, Caddy builder/runtime image tags,
  `xcaddy` plugin list, `authdbctl` image installation, or OCI labels
- `github`: GitHub Actions workflows and repository GitHub metadata
- `goreleaser`: GoReleaser packaging and release artifact configuration
- `ops`: Makefile automation, version sync, release procedure, repository
  maintenance, or deliberately cross-cutting operational work
- `release`: release-only version metadata when the change is not created by
  existing release automation
- `security`: vulnerability fixes, hardening, dependency-audit work, or
  disclosure-policy changes
- `skills`: AI agent skills, skill metadata, `AGENTS.md`, or agent-facing
  repository instructions
- `docs`: documentation-only changes
- `tests`: test additions, fixture updates, or validation-only changes
- `fix`: correctness fix without a known production breakage
- `feat`: user-facing capability that does not fit a more specific surface
- `various`: intentionally mixed changes that do not fit one indicator

Older repository history contains subjects such as `released v1.0.41`,
`upgraded to caddy-security v1.1.62`, and
`upgrade to github.com/greenpau/caddy-security v1.1.58`. Treat those as
existing automation/history, not as templates for new hand-written messages.
Prefer colon-form subjects such as:

```text
ops: upgrade caddy-security to v1.1.63
docker: add authdbctl image smoke check
skills: add repo-local agent guidance
```

## Commit Message Body

The commit message body must contain these sections in this order:

1. `Before this commit:`
2. `After this commit:`
3. `Tests:`
4. `More info:`

The body may also contain these optional sections:

1. `Resolves:`
2. `Partial Resolution:`
3. `See also:`
4. `Links:`

Body rules:

- Separate sections with one blank line.
- Each section title MUST end with a colon (`:`).
- Lines MUST NOT exceed 87 characters, except in `Links` and `More info`.
- Use `Resolves` only when the PR or commit resolves an issue completely.
- Use `Partial Resolution` when the PR or commit addresses an issue partially.
- Use `See also` for additional related references.
- `Resolves`, `Partial Resolution`, and `See also` MUST contain valid links.
- Multiple links in those reference sections MUST be separated by comma and
  space (`, `).
- `Tests` MUST describe the command or manual check performed.
- If no smoke test was run, `Tests` MUST say `not run` and include the reason.
- `More info` MUST summarize implementation details or notable decisions.

Use this template:

```text
indicator: concise subject under 87 characters

Before this commit: describe the previous behavior, limitation, or state.

After this commit: describe the new behavior, implementation, or state.

Tests: describe the command or manual check performed.

More info: summarize important implementation details or decisions.
```

## Commit Message File Workflow

When asked to "create commit message for the change", create a file in
`tmp/commits` and place the commit message in that file. Commit message files in
`tmp/commits` are working artifacts and should not be committed unless
explicitly requested. Prefix the file name with `YYYYMMDD_HHMM_`.
