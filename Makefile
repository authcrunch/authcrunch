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

.PHONY: release
release:
	@echo "$@: started"
	@go mod tidy
	@go mod verify
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
