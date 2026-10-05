# authcrunch

<a href="https://github.com/greenpau/caddy-security/actions/workflows/build.yml" target="_blank"><img src="https://github.com/greenpau/caddy-security/actions/workflows/build.yml/badge.svg"></a>

Authentication Portal based on [Caddy Security](https://github.com/greenpau/caddy-security).

Run `make sync` to update dependency versions, verify modules, and rebuild. The
target also stages `Dockerfile`, `Makefile`, `VERSION`, `go.mod`, and `go.sum` and
prints a suggested commit command.

Module synchronization uses `https://proxy.golang.org,direct`, even if your local
Go configuration sets `GOPROXY=direct`. This retrieves the published module
contents when an upstream tag has moved, while preserving Go's checksum
verification. To use a different proxy, run
`make sync SYNC_GOPROXY=https://your-module-proxy.example.com,direct`.

If a direct download fails with a checksum mismatch, the upstream tag may have
changed after publication. For example, `caddy-security`'s `v1.4.0` tag moved after
Go recorded its original contents. Use the verified proxy copy; changed contents
must be published under a new version. Do not disable checksum verification to
accept a changed tag. See [Go's module authentication documentation](https://go.dev/ref/mod#authenticating).

AuthCrunch releases use the `caddy-security` version pinned in `go.mod`. For
example, `caddy-security v1.4.1` produces AuthCrunch `v1.4.1`, `VERSION` containing
`1.4.1`, and an image version label of `1.4.1`. `make sync` updates and stages this
metadata along with the dependency pins.

After running `make sync` and committing your changes on `main`, run `make release`
to verify modules and version consistency, tag that commit, and push the branch
and that tag. It does not modify or increment `VERSION`. An existing release tag
is rejected; release a new `caddy-security` version before publishing another
AuthCrunch version.
`make check-release-version` checks local metadata, and
`make check-release-version RELEASE_TAG=v1.4.1` also checks a proposed tag.
