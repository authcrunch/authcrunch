APP_NAME="authcrunch"
APP_VERSION:=$(shell cat VERSION | head -1)
GIT_COMMIT:=$(shell git describe --dirty --always)
GIT_BRANCH:=$(shell git rev-parse --abbrev-ref HEAD -- | head -1)
LATEST_GIT_COMMIT:=$(shell git log --format="%H" -n 1 | head -1)
BUILD_USER:=$(shell whoami)
BUILD_DATE:=$(shell date +"%Y-%m-%d")
BUILD_DIR:=$(shell pwd)

all: build_info build
	@echo "$@: complete"

.PHONY: build_info
build_info:
	@echo "Version: $(APP_VERSION), Branch: $(GIT_BRANCH), Revision: $(GIT_COMMIT)"
	@echo "Build on $(BUILD_DATE) by $(BUILD_USER)"

.PHONY: build
build:
	@echo "$@: started"
	@rm -rf ./bin/$(APP_NAME)
	@go build -v -o ./bin/$(APP_NAME) main.go
	@./bin/$(APP_NAME) version
	@./bin/$(APP_NAME) fmt ./Caddyfile --overwrite
	@#bin/$(APP_NAME) validate --config ./Caddyfile
	@echo "$@: complete"

.PHONY: dep
dep:
	@echo "$@: started"
	@versioned || go install github.com/greenpau/versioned/cmd/versioned@latest
	@echo "$@: complete"


.PHONY: sync
sync:
	@echo "$@: started"
	$(eval TRACE_PLUGIN_VERSION=$(shell git -c 'versionsort.suffix=-' ls-remote --exit-code --refs --sort='version:refname' --tags https://github.com/greenpau/caddy-trace '*.*.*' | tail --lines=1 | cut -f2 | cut -d"/" -f3 | sed 's/v//'))
	@echo "$@: caddy-trace version: ${TRACE_PLUGIN_VERSION}"
	$(eval CS_AWS_SM_PLUGIN_VERSION=$(shell git -c 'versionsort.suffix=-' ls-remote --exit-code --refs --sort='version:refname' --tags https://github.com/greenpau/caddy-security-secrets-aws-secrets-manager '*.*.*' | tail --lines=1 | cut -f2 | cut -d"/" -f3 | sed 's/v//'))
	@echo "$@: caddy-security-secrets-aws-secrets-manager version: ${CS_AWS_SM_PLUGIN_VERSION}"
	$(eval TARGET_LIB_VERSION=$(shell git -c 'versionsort.suffix=-' ls-remote --exit-code --refs --sort='version:refname' --tags https://github.com/greenpau/go-authcrunch '*.*.*' | tail --lines=1 | cut -f2 | cut -d"/" -f3 | sed 's/v//'))
	@echo "$@: go-authcrunch version: ${TARGET_LIB_VERSION}"
	$(eval TARGET_PLUGIN_VERSION=$(shell git -c 'versionsort.suffix=-' ls-remote --exit-code --refs --sort='version:refname' --tags https://github.com/greenpau/caddy-security '*.*.*' | tail --lines=1 | cut -f2 | cut -d"/" -f3 | sed 's/v//'))
	@echo "$@: caddy-security version: ${TARGET_PLUGIN_VERSION}"
	@sed -i '' 's/org.opencontainers.image.version=[0-9]\.[0-9]*\.[0-9]*/org.opencontainers.image.version='"${TARGET_LIB_VERSION}"'/' Dockerfile
	@sed -i '' 's/caddy-security v[0-9]\.[0-9]*\.[0-9]*/caddy-security v'"${TARGET_PLUGIN_VERSION}"'/' go.mod
	@sed -i '' 's/caddy-security@v[0-9]\.[0-9]*\.[0-9]*/caddy-security@v'"${TARGET_PLUGIN_VERSION}"'/' Dockerfile
	@sed -i '' 's/caddy-security-secrets-aws-secrets-manager@v[0-9]\.[0-9]*\.[0-9]*/caddy-security-secrets-aws-secrets-manager@v'"${CS_AWS_SM_PLUGIN_VERSION}"'/' Dockerfile
	@sed -i '' 's/caddy-trace@v[0-9]\.[0-9]*\.[0-9]*/caddy-trace@v'"${TRACE_PLUGIN_VERSION}"'/' Dockerfile
	@go mod tidy
	@go mod verify
	@echo "$@: complete"

.PHONY: release
release:
	@echo "$@: started"
	@go mod tidy;
	@go mod verify;
	@if [ $(GIT_BRANCH) != "main" ]; then echo "cannot release to non-main branch $(GIT_BRANCH)" && false; fi
	@git diff-index --quiet HEAD -- || ( echo "git directory is dirty, commit changes first" && false )
	@versioned -patch
	@echo "Patched version"
	@git add VERSION
	@git commit -m "released v`cat VERSION | head -1`"
	@git tag -a v`cat VERSION | head -1` -m "v`cat VERSION | head -1`"
	@git push
	@git push --tags
	@echo "$@: complete"
