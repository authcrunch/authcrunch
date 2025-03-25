FROM caddy:2.9.1-builder AS builder

LABEL org.opencontainers.image.title=authcrunch
LABEL org.opencontainers.image.description="Authentication Portal"
LABEL org.opencontainers.image.url=https://github.com/greenpau/caddy-security
LABEL org.opencontainers.image.source=https://github.com/greenpau/caddy-security
LABEL org.opencontainers.image.version=1.0.1
LABEL maintainer="greenpau"

RUN GOTOOLCHAIN=go1.24.1 xcaddy build \
    --with github.com/greenpau/caddy-security@v1.1.30 \
    --with github.com/greenpau/caddy-security-secrets-aws-secrets-manager@latest \
    --with github.com/greenpau/caddy-trace@latest \
    --with github.com/caddy-dns/cloudflare

FROM caddy:2.9.1

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
