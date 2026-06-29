---
name: dockerfile-management
description: authcrunch Dockerfile and container image management guidance, including Caddy builder/runtime image versions, xcaddy plugin pins, authdbctl installation, OCI labels, GHCR Buildx publishing, beta image sync behavior, and Docker validation commands. Use when changing the top-level Dockerfile, Docker image contents, plugin image versions, build args, container labels, Docker workflow, or image validation steps.
---

# Dockerfile Management

## Overview

Use this skill for Dockerfile and image-publishing work in this repository. The
container image is a custom Caddy runtime built with `xcaddy` plus an installed
`authdbctl` helper.

If the task is primarily about Makefile target selection or release procedure,
also use the repo-local `scripts-and-automation` skill. If the task is
primarily about CI reproduction, also use `testing-and-ci`.

## Dockerfile Structure

The Dockerfile has two stages:

- `FROM caddy:<version>-builder AS builder`
- `FROM caddy:<version>`

Keep the builder and runtime Caddy image versions aligned unless the user
explicitly asks for a split-version test.

The builder stage runs `xcaddy build` with these plugins:

```text
github.com/greenpau/caddy-security
github.com/greenpau/caddy-security-secrets-aws-secrets-manager
github.com/greenpau/caddy-trace
github.com/caddy-dns/cloudflare
```

The first three are pinned in the Dockerfile and are also represented in the Go
module or runtime wiring. The Cloudflare DNS module is currently Docker-only.
When adding or removing Caddy modules, check whether `main.go`, `go.mod`, and
the Dockerfile should stay aligned.

The builder stage also installs:

```text
github.com/greenpau/go-authcrunch/cmd/authdbctl@latest
```

The runtime stage copies `/usr/bin/caddy` and `/go/bin/authdbctl`, then runs
`authdbctl --version` as a build-time smoke check.

## Version Management

Prefer the Makefile sync workflow for routine plugin version updates:

```bash
make sync-versions
make sync-mod
make build
```

`make sync-versions` queries remote tags and rewrites Dockerfile pins for:

```text
github.com/greenpau/caddy-security
github.com/greenpau/caddy-security-secrets-aws-secrets-manager
github.com/greenpau/caddy-trace
```

It also rewrites `org.opencontainers.image.version` from the latest
`github.com/greenpau/go-authcrunch` tag. Do not assume that label matches this
repository's top-level `VERSION`; GitHub Docker release tags use `VERSION`.

When manually changing dependency versions, update all relevant places:

```text
Dockerfile
go.mod
go.sum
main.go
.github/workflows/docker.yml
```

Run `go mod tidy` and `go mod verify` after dependency changes when network
access is available.

## Docker Workflow

`.github/workflows/docker.yml` uses Docker Buildx and pushes to GHCR.

Manual `release` publishing:

- Reads `VERSION` into `PKG_VERSION`.
- Builds `linux/amd64` and `linux/arm64`.
- Pushes `ghcr.io/<owner>/authcrunch:v<PKG_VERSION>`.
- Pushes `ghcr.io/<owner>/authcrunch:latest`.

Scheduled or manual `beta` publishing:

- Runs `make sync`.
- Prints `git diff Dockerfile`.
- Builds `linux/amd64` and `linux/arm64`.
- Pushes `ghcr.io/<owner>/authcrunch:beta`.

If adding Docker build arguments in the workflow, add matching `ARG` statements
to the Dockerfile or remove unused build args.

## Validation

Use these checks when Docker is available:

```bash
docker build -t authcrunch:local .
docker run --rm authcrunch:local version
docker run --rm --entrypoint authdbctl authcrunch:local --version
```

For Buildx parity with CI, validate at least one platform locally:

```bash
docker buildx build --platform linux/amd64 -t authcrunch:local --load .
```

Multi-platform Buildx builds, `xcaddy build`, `go install`, and base image
pulls may require network access and a Docker daemon.

## Guardrails

- Do not run Docker publish workflows, push images, or log in to GHCR unless the
  user explicitly asks.
- Do not run `make sync` just to validate a Dockerfile edit; it can rewrite
  dependency versions and stage files through `sync-commit`.
- Review `Dockerfile`, `go.mod`, `go.sum`, and `Caddyfile` diffs after sync or
  build targets.
- Keep OCI labels accurate when repository ownership, image source, or product
  description changes.
