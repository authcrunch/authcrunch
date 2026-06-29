---
name: scripts-and-automation
description: authcrunch repository automation, Makefile target selection, local build commands, dependency and plugin version synchronization, generated artifact handling, release workflows, GoReleaser behavior, and guardrails for networked or destructive automation. Use when choosing, running, documenting, or updating repository scripts and Make targets; troubleshooting build automation; deciding whether generated outputs belong in a change; or preparing releases for this Go module.
---

# Scripts and Automation

## Overview

Use the Makefile as the primary automation surface for this Go module. There is
no top-level `scripts/` directory; local automation lives in `Makefile`,
`.github/workflows`, `.goreleaser.yaml`, and the top-level `Dockerfile`.

Prefer direct `go test` or `go build` commands for narrow validation while
editing. Use Makefile targets when the user asks for repository workflow
behavior, dependency/version sync, release work, or CI-like validation.

## Command Selection

- Use `go test ./...` for a fast module check without formatting `Caddyfile` or
  touching generated binaries.
- Use `go build -v -o ./bin/authcrunch main.go` for a direct binary build.
- Use `make` for the default repository build. It runs `build_info` and
  `build`.
- Use `make build` to delete and rebuild `bin/authcrunch`, run
  `bin/authcrunch version`, and format `Caddyfile` in place.
- Use `make dep` to ensure `versioned` is installed or install it with
  `go install github.com/greenpau/versioned/cmd/versioned@latest`.
- Use `make sync-mod` to run `go mod tidy` and `go mod verify`.
- Use `make sync-versions` to update dependency/plugin versions from remote Git
  tags in `Dockerfile` and `go.mod`.
- Use `make sync` only when the full update flow is intended. It chains
  `sync-versions`, `sync-mod`, `build`, and `sync-commit`.
- Use `make clean` only if a cleanup target is added in the future; this
  Makefile currently does not define one.

## Version Sync Workflow

`make sync-versions` queries remote tags for:

```text
github.com/greenpau/caddy-trace
github.com/greenpau/caddy-security-secrets-aws-secrets-manager
github.com/greenpau/go-authcrunch
github.com/greenpau/caddy-security
```

It then rewrites:

```text
Dockerfile
go.mod
```

The `org.opencontainers.image.version` label tracks the latest
`go-authcrunch` tag selected by the sync target. The GHCR release tag in the
Docker workflow uses this repository's top-level `VERSION` file instead.

After dependency sync, run or expect:

```bash
go mod tidy
go mod verify
make build
```

Review `Dockerfile`, `go.mod`, `go.sum`, and `Caddyfile` diffs separately. Do
not keep version churn that was produced by a broader target unless the user
asked for that workflow.

## Makefile Side Effects

Treat these targets as mutating commands:

- `build`: removes/recreates `bin/authcrunch` and rewrites `Caddyfile`.
- `sync-versions`: rewrites `Dockerfile` and `go.mod`.
- `sync-mod`: can rewrite `go.mod` and `go.sum`.
- `sync`: performs all sync/build side effects and then runs `sync-commit`.
- `sync-commit`: stages `Dockerfile`, `Makefile`, `go.mod`, and `go.sum`, then
  prints the intended commit command. It does not create the commit.
- `release`: patches `VERSION`, commits, creates an annotated tag, pushes
  commits, and pushes tags.

`make dep`, `make sync-versions`, `make sync`, `go mod tidy`, `go mod verify`,
`go mod download`, `go install`, Docker builds, and GoReleaser may require
network access.

## Release Guardrails

Treat release targets as human-operator actions unless the user explicitly asks
for a release workflow.

- `make release` runs module tidy/verify.
- It requires the current branch to be `main`.
- It requires a clean git worktree.
- It runs `versioned -patch`.
- It stages `VERSION`.
- It creates a release commit with `released v<VERSION>`.
- It creates an annotated `v<VERSION>` tag.
- It pushes commits and tags.

Never push commits or tags, create release tags, or run `make release` unless
the user explicitly requested that action.

## Generated Artifacts

Do not treat generated outputs as source changes unless the user explicitly
asks to update or commit them:

```text
bin/authcrunch
.coverage/
.doc/
.tmp/
dist/
```

Review source files touched by automation before including them:

```text
Caddyfile
Dockerfile
Makefile
VERSION
go.mod
go.sum
```

## CI Notes

The build workflow runs on Ubuntu with Go `1.25.x`. It installs `make` and
`libnss3-tools`, runs `make dep`, `go mod tidy`, `go mod verify`,
`go mod download`, and `make`.

The Docker workflow uses Buildx and pushes to GHCR. Manual release publishing
uses `VERSION` for `v<VERSION>` and `latest`; nightly or beta publishing runs
`make sync` before building the `beta` image.

The release workflow runs GoReleaser on `v*` tags. `.goreleaser.yaml` builds
`./` for Linux, Windows, and Darwin on `amd64` and `arm64` with `-mod=readonly`.
