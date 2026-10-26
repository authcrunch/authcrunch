FROM caddy:2.11.7-builder AS builder

RUN xcaddy build \
    --with github.com/greenpau/caddy-security@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/claims-enrichment-static@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/credential-authenticators-consul@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/credential-authenticators-sqlite@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/cryptographic-signing-rsapss@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/external-authorization-httpjson@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/identity-providers-consul@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/identity-providers-sqlite@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/identity-stores-consul@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/identity-stores-sqlite@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/messaging-sqlite@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/oauth-login-storage-consul@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/oauth-login-storage-sqlite@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/registration-workflows-sqlite@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/secrets-consul@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/secrets-sqlite@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/session-and-refresh-storage-consul@v1.5.0 \
    --with github.com/greenpau/caddy-security/plugins/session-and-refresh-storage-sqlite@v1.5.0 \
    --with github.com/greenpau/caddy-security-secrets-aws-secrets-manager@v1.0.1 \
    --with github.com/greenpau/caddy-trace@v1.1.13 \
    --with github.com/pteich/caddy-tlsconsul@v1.5.0 \
    --with github.com/caddy-dns/cloudflare

RUN go install github.com/greenpau/go-authcrunch/cmd/authdbctl@latest

FROM caddy:2.11.7

LABEL org.opencontainers.image.title=authcrunch
LABEL org.opencontainers.image.description="Authentication Portal"
LABEL org.opencontainers.image.url=https://github.com/greenpau/caddy-security
LABEL org.opencontainers.image.source=https://github.com/greenpau/caddy-security
LABEL org.opencontainers.image.version=1.5.0
LABEL maintainer="greenpau"

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

COPY --from=builder /go/bin/authdbctl /usr/bin/authdbctl

RUN authdbctl --version
