# Repository Guidelines

## Project Summary

`authcrunch` delivers a Docker-packaged Authentication Portal experience based on
Caddy Security. It builds a custom Caddy runtime with AuthCrunch security
modules, AWS Secrets Manager support, tracing, and the `authdbctl` management
CLI so operators can consume the portal as a ready-to-run container image.

## Scripts and Automation

Use the repo-local `scripts-and-automation` skill when choosing, running, or
documenting Makefile targets, dependency/version sync commands, local build
commands, release procedures, generated artifacts, or automation side effects.

## Testing and CI

Use the repo-local `testing-and-ci` skill when choosing or running validation,
reproducing GitHub Actions locally, interpreting build/release/Docker workflow
failures, or documenting the tests/checks performed for this repository.

## Source Code Management

Use the repo-local `source-code-management` skill for commit message rules and
for the workflow used when asked to create a commit message for a change.

## Dockerfile Management

Use the repo-local `dockerfile-management` skill when changing the top-level
`Dockerfile`, Docker image contents, Caddy/plugin image versions, `authdbctl`
installation, OCI labels, Buildx settings, or the Docker publish workflow.
