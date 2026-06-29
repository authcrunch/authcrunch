#!/bin/bash
set -euo pipefail

CURRENT_REF="${CURRENT_REF:-HEAD}"
WORK_DIR="${RUNNER_TEMP:-/tmp}"

MODULE_NAMES=(
	"github.com/greenpau/caddy-security"
	"github.com/greenpau/go-authcrunch"
)
MODULE_REPOS=(
	"https://github.com/greenpau/caddy-security"
	"https://github.com/greenpau/go-authcrunch"
)
MODULE_TITLES=(
	"caddy-security"
	"go-authcrunch"
)
MODULE_ENV_PREFIXES=(
	"CADDY_SECURITY"
	"GO_AUTHCRUNCH"
)

module_version_from_file() {
	local module="$1"

	awk -v module="${module}" '$1 == module { print $2; exit }' go.mod
}

module_version_from_ref() {
	local ref="$1"
	local module="$2"

	git show "${ref}:go.mod" 2>/dev/null \
		| awk -v module="${module}" '$1 == module { print $2; exit }' || true
}

previous_release_ref() {
	git describe --tags --abbrev=0 --match "v*" "${CURRENT_REF}^{commit}^" 2>/dev/null || true
}

module_repo_dir() {
	local repo_url="$1"
	local title="$2"
	local env_prefix="$3"
	local repo_env_var="${env_prefix}_REPO"
	local repo_override="${!repo_env_var:-}"

	if [ -n "${repo_override}" ]; then
		printf "%s\n" "${repo_override}"
		return
	fi

	if [ -d "../${title}/.git" ]; then
		printf "%s\n" "../${title}"
		return
	fi

	local repo_dir
	repo_dir="$(mktemp -d "${WORK_DIR}/${title}.XXXXXX")"
	if git clone --filter=blob:none --no-checkout "${repo_url}.git" "${repo_dir}" >/dev/null 2>&1; then
		printf "%s\n" "${repo_dir}"
	fi
}

module_changelog() {
	local module="$1"
	local repo_url="$2"
	local title="$3"
	local env_prefix="$4"
	local previous_ref="$5"
	local previous_version_env_var="${env_prefix}_PREVIOUS_VERSION"
	local current_version_env_var="${env_prefix}_CURRENT_VERSION"
	local previous_version="${!previous_version_env_var:-}"
	local current_version="${!current_version_env_var:-}"

	if [ -z "${previous_version}" ] && [ -n "${previous_ref}" ]; then
		previous_version="$(module_version_from_ref "${previous_ref}" "${module}")"
	fi

	if [ -z "${current_version}" ]; then
		current_version="$(module_version_from_file "${module}")"
	fi

	if [ -z "${previous_version}" ] || [ -z "${current_version}" ]; then
		return
	fi

	if [ "${previous_version}" = "${current_version}" ]; then
		return
	fi

	local compare_url="${repo_url}/compare/${previous_version}...${current_version}"

	printf "## %s changes\n\n" "${title}"
	printf "%s was updated from \`%s\` to \`%s\`.\n\n" "${module}" "${previous_version}" "${current_version}"
	printf "Compare: %s\n" "${compare_url}"

	local repo_dir
	repo_dir="$(module_repo_dir "${repo_url}" "${title}" "${env_prefix}")"
	if [ -z "${repo_dir}" ]; then
		return
	fi

	if ! git -C "${repo_dir}" rev-parse --verify --quiet "refs/tags/${previous_version}" >/dev/null; then
		return
	fi

	if ! git -C "${repo_dir}" rev-parse --verify --quiet "refs/tags/${current_version}" >/dev/null; then
		return
	fi

	local commit_log
	commit_log="$(
		git -C "${repo_dir}" log --reverse --format='- %s (%h)' \
			"${previous_version}..${current_version}" 2>/dev/null || true
	)"

	if [ -z "${commit_log}" ]; then
		return
	fi

	printf "\n%s\n" "${commit_log}"
}

previous_ref="${PREVIOUS_REF:-$(previous_release_ref)}"
printed=0

for index in "${!MODULE_NAMES[@]}"; do
	section="$(
		module_changelog \
			"${MODULE_NAMES[${index}]}" \
			"${MODULE_REPOS[${index}]}" \
			"${MODULE_TITLES[${index}]}" \
			"${MODULE_ENV_PREFIXES[${index}]}" \
			"${previous_ref}"
	)"

	if [ -z "${section}" ]; then
		continue
	fi

	if [ "${printed}" -eq 1 ]; then
		printf "\n"
	fi
	printf "%s\n" "${section}"
	printed=1
done
