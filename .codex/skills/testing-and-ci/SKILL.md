---
name: testing-and-ci
description: authcrunch repository testing and CI workflow guidance, including Go command selection, Makefile build validation, Caddyfile formatting side effects, GitHub Actions build/release/Docker behavior, GoReleaser packaging, and generated artifact handling. Use when choosing or running tests, validating changes, interpreting CI failures, reproducing GitHub Actions locally, or documenting validation for this AuthCrunch Caddy distribution.
---

# Testing and CI

## Overview

Use this skill for validation and CI reproduction in the `authcrunch`
repository. The repo builds a custom Caddy binary; there are no package-specific
unit tests in this small wrapper module unless tests are added later.

The Go module is rooted at the repository top level and currently declares Go
`1.25.8`. If the task becomes release, dependency sync, Docker image management,
or general automation work rather than test/CI work, also use the repo-local
`scripts-and-automation` or `dockerfile-management` skill.

## Command Selection

Use direct Go commands for quick feedback:

```bash
go test ./...
go test -run <TestName> ./...
go build -v -o ./bin/authcrunch main.go
```

Use `make` or `make build` when validation should match the repository build
workflow. The `build` target deletes `./bin/authcrunch`, runs `go build`, runs
`./bin/authcrunch version`, and formats `Caddyfile` in place with
`./bin/authcrunch fmt ./Caddyfile --overwrite`.

Use this sequence to reproduce the build workflow locally:

```bash
make dep
go mod tidy
go mod verify
go mod download
make
```

`make dep`, `go mod tidy`, `go mod verify`, `go mod download`, Docker builds,
GoReleaser, and version sync commands may require network access.

## Makefile Side Effects

Treat Makefile targets as potentially mutating commands.

- `make build` removes and recreates `bin/authcrunch`.
- `make build` rewrites `Caddyfile` using the built Caddy formatter.
- `make sync-versions` queries remote Git tags and rewrites `Dockerfile` and
  `go.mod` versions.
- `make sync-mod` runs `go mod tidy` and `go mod verify`, which can rewrite
  `go.mod` and `go.sum`.
- `make sync` chains version sync, module sync, build, and sync-commit output.
- `make release` runs module tidy/verify, requires branch `main`, requires a
  clean worktree, patches `VERSION`, commits, tags, pushes commits, and pushes
  tags.

Review the diff after Makefile targets before keeping generated source changes.
Generated `Caddyfile`, `go.mod`, `go.sum`, `Dockerfile`, or `VERSION` changes
are intentional only when the user asked for that workflow.

## CI Workflows

`.github/workflows/build.yml` runs on pushes and pull requests to `main`. It
uses Ubuntu and Go `1.25.x`, installs `make` and `libnss3-tools`, runs
`make dep`, `go mod tidy`, `go mod verify`, `go mod download`, and `make`.

If CI fails in the build job, reproduce with:

```bash
make dep
go mod tidy
go mod verify
go mod download
make
```

`.github/workflows/docker.yml` runs on manual dispatch and nightly schedule. It
builds and pushes multi-platform images to GHCR. Release publishing tags
`v<VERSION>` and `latest`; scheduled or beta publishing runs `make sync`, shows
`git diff Dockerfile`, then pushes the `beta` tag.

`.github/workflows/release.yml` runs GoReleaser on `v*` tags with Go `~1.25`.
Treat release tags, pushes, and GoReleaser publication as human-operator actions
unless the user explicitly requests them.

## Adding Validation

For changes to `main.go`, module dependencies, or Caddy plugin wiring, run:

```bash
go test ./...
make
```

For changes to `Caddyfile`, run `make build` and inspect the formatted
`Caddyfile` diff.

For changes to `.goreleaser.yaml`, run a local snapshot only when GoReleaser is
available and the user wants packaging validation:

```bash
goreleaser release --snapshot --clean
```

For Dockerfile or Docker workflow changes, use the `dockerfile-management` skill
for image-specific validation commands.

## Generated Artifacts

Treat these as generated outputs unless the user explicitly asks to preserve or
commit them:

```text
bin/authcrunch
.coverage/
.doc/
.tmp/
dist/
```

Also review source diffs from automation carefully:

```text
Caddyfile
Dockerfile
VERSION
go.mod
go.sum
```
