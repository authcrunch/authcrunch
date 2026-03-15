FROM caddy:2.11.2-builder AS builder

RUN xcaddy build \
    --with github.com/greenpau/caddy-security@latest \
    --with github.com/greenpau/caddy-security-secrets-aws-secrets-manager@latest \
    --with github.com/greenpau/caddy-trace@latest \
    --with github.com/caddy-dns/cloudflare

RUN go install github.com/greenpau/go-authcrunch/cmd/authdbctl@latest

FROM caddy:2.11.2

LABEL org.opencontainers.image.title=authcrunch
LABEL org.opencontainers.image.description="Authentication Portal"
LABEL org.opencontainers.image.url=https://github.com/greenpau/caddy-security
LABEL org.opencontainers.image.source=https://github.com/greenpau/caddy-security
LABEL org.opencontainers.image.version=1.1.23
LABEL maintainer="greenpau"

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

COPY --from=builder /go/bin/authdbctl /usr/bin/authdbctl

RUN authdbctl --version