#!/usr/bin/env bash
# Prepare all Go source and test dependencies before the scanner goes offline.
set -euo pipefail

repository_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
audit_dir="${OSS_SCANNER_WORK:-/opt/oss-scanner}"
mkdir -p "$audit_dir/foundation" "$audit_dir/bin"
cd "$repository_dir"

go mod download
go mod verify
go build -mod=readonly -p 2 -o "$audit_dir/bin/authcrunch" .
"$audit_dir/bin/authcrunch" version
go version -m "$audit_dir/bin/authcrunch" > "$audit_dir/build-info.txt"

# Copy the versions selected by this checkout, rather than unrelated latest
# branches. Keep the shared Go module cache intact and the audit copies writable.
for name in caddy-security go-authcrunch; do
    module="github.com/greenpau/$name"
    source_dir="$(go list -m -f '{{.Dir}}' "$module")"
    destination="$audit_dir/foundation/$name"
    if [[ -e "$destination" ]]; then
        echo "Refusing to overwrite an existing audit source directory: $destination" >&2
        exit 1
    fi
    cp -R "$source_dir" "$destination"
    chmod -R u+w "$destination"
    (
        cd "$destination"
        go mod download
        go mod verify
        # Compile, without running, the full root-module tests. Constrain
        # compiler parallelism; expensive integration journeys run on demand.
        go test -mod=readonly -p 2 -run '^$' ./...
    )
done

go list -m -json all > "$audit_dir/modules.json"
