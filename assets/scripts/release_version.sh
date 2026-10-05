#!/bin/bash
set -euo pipefail

# Run from the repository root. go.mod is the source of the release version.
mode="${1:-print}"
release_tag="${2:-}"

fail() {
	printf 'release-version: %s\n' "$*" >&2
	exit 1
}

case "${mode}" in
	print|sync|check) ;;
	*) fail "usage: $0 [print|sync|check [release-tag]]" ;;
esac

plugin_version="$(awk '
	$1 == "github.com/greenpau/caddy-security" { print $2 }
	$1 == "require" && $2 == "github.com/greenpau/caddy-security" { print $3 }
' go.mod)"
semver='^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$'
[[ "${plugin_version}" =~ ${semver} ]] \
	|| fail "go.mod must pin a caddy-security release version (got '${plugin_version}')"
version="${plugin_version#v}"

docker_version="$(awk '
	$1 == "--with" && index($2, "github.com/greenpau/caddy-security@") == 1 {
		sub(/^.*@/, "", $2); print $2
	}
' Dockerfile)"
[[ "${docker_version}" == "${plugin_version}" ]] \
	|| fail "Dockerfile pins '${docker_version}', but go.mod pins '${plugin_version}'; run make sync first"

case "${mode}" in
	print)
		printf '%s\n' "${version}"
		;;
	sync)
		[[ "$(awk '/^LABEL org\.opencontainers\.image\.version=/ { count++ } END { print count+0 }' Dockerfile)" == 1 ]] \
			|| fail "Dockerfile must contain one org.opencontainers.image.version label"
		tmp_file="$(mktemp "${TMPDIR:-/tmp}/authcrunch-version.XXXXXX")"
		trap 'rm -f "${tmp_file}"' EXIT
		sed "s/^LABEL org\.opencontainers\.image\.version=.*/LABEL org.opencontainers.image.version=${version}/" Dockerfile > "${tmp_file}"
		cat "${tmp_file}" > Dockerfile
		printf '%s\n' "${version}" > VERSION
		printf 'release-version: synchronized to %s\n' "${plugin_version}"
		;;
	check)
		[[ "$(cat VERSION)" == "${version}" ]] \
			|| fail "VERSION must be ${version}; run make sync"
		[[ "$(sed -n 's/^LABEL org\.opencontainers\.image\.version=//p' Dockerfile)" == "${version}" ]] \
			|| fail "Docker image version must be ${version}; run make sync"
		[[ -z "${release_tag}" || "${release_tag}" == "${plugin_version}" ]] \
			|| fail "release tag '${release_tag}' must be '${plugin_version}'"
		printf 'release-version: %s matches caddy-security\n' "${plugin_version}"
		;;
esac
