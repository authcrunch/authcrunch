# Audit environment: keep source, compilers, module caches and browser tooling.
# The production Dockerfile intentionally contains only the packaged runtime.
FROM golang:1.26.8-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    GOPROXY=https://proxy.golang.org,direct \
    GOTOOLCHAIN=local \
    GOMAXPROCS=2 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates build-essential git make openssl python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Required by the OSS Scanner image contract.
COPY . /src
WORKDIR /src

# Fetch exact dependencies, preserve editable copies of the two foundation
# libraries, and compile their tests while network access is still available.
RUN bash .oss-scanner/prepare.sh

# Prime the same isolated tool environment used by make e2e-login-test.
# Playwright installs the browser's OS libraries during this online build only.
RUN E2E_LOGIN_INSTALL_DEPS=1 python3 - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, "/src/assets/scripts")
from e2e_login import prepare_tools
output = Path("/opt/oss-scanner/setup")
output.mkdir(parents=True, exist_ok=True)
prepare_tools(output)
PY

# Audits and rebuilds must use the prepared environment, without remote lookups.
ENV GOPROXY=off

RUN go test -mod=readonly ./... \
    && make test-automation

CMD ["bash"]
