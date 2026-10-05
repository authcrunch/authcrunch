# authcrunch

<a href="https://github.com/greenpau/caddy-security/actions/workflows/build.yml" target="_blank"><img src="https://github.com/greenpau/caddy-security/actions/workflows/build.yml/badge.svg"></a>

Authentication Portal based on [Caddy Security](https://github.com/greenpau/caddy-security).

Run `make sync` to update dependency versions, verify modules, and rebuild. The
target also stages `Dockerfile`, `Makefile`, `go.mod`, and `go.sum` and prints a
suggested commit command.

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
