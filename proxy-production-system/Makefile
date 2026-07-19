BIN := bin/proxy
GO := GOWORK=off go
VERSION ?= dev
COMMIT ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
BUILD_DATE ?= $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
DIST_DIR := dist
RELEASE_NAME := proxy-$(VERSION)-linux-amd64
LDFLAGS := -X 'proxy-production-system/internal/buildinfo.Version=$(VERSION)' -X 'proxy-production-system/internal/buildinfo.Commit=$(COMMIT)' -X 'proxy-production-system/internal/buildinfo.BuildDate=$(BUILD_DATE)'

.PHONY: test test-race vet fmt-check build run quality security-test package release-ready eval eval-stack clean

test:
	$(GO) test ./...

test-race:
	$(GO) test -race ./...

vet:
	$(GO) vet ./...

fmt-check:
	@files="$$(rg --files --glob '*.go')"; \
	if [ -z "$$files" ]; then \
		echo "No Go files found for formatting check."; \
		exit 0; \
	fi; \
	unformatted="$$(gofmt -l $$files)"; \
	if [ -n "$$unformatted" ]; then \
		echo "Go files need formatting:"; \
		echo "$$unformatted"; \
		echo "Run: gofmt -w <files>"; \
		exit 1; \
	fi

build:
	GOWORK=off CGO_ENABLED=0 go build -ldflags "$(LDFLAGS)" -o $(BIN) ./cmd/proxy

run:
	GOWORK=off PROXY_UPSTREAMS=http://localhost:8081,http://localhost:8082 go run ./cmd/proxy

quality: fmt-check test test-race vet build

security-test:
	./scripts/security-test.sh

package: clean build
	@mkdir -p $(DIST_DIR)/$(RELEASE_NAME)
	@cp $(BIN) $(DIST_DIR)/$(RELEASE_NAME)/proxy
	@cp README.md $(DIST_DIR)/$(RELEASE_NAME)/README.md
	@cp -r deployments $(DIST_DIR)/$(RELEASE_NAME)/deployments
	@cp -r docs $(DIST_DIR)/$(RELEASE_NAME)/docs
	@cp -r scripts $(DIST_DIR)/$(RELEASE_NAME)/scripts
	@cp .env.example $(DIST_DIR)/$(RELEASE_NAME)/.env.example
	@echo "version=$(VERSION)" > $(DIST_DIR)/$(RELEASE_NAME)/BUILD_INFO
	@echo "commit=$(COMMIT)" >> $(DIST_DIR)/$(RELEASE_NAME)/BUILD_INFO
	@echo "build_date=$(BUILD_DATE)" >> $(DIST_DIR)/$(RELEASE_NAME)/BUILD_INFO
	@tar -C $(DIST_DIR) -czf $(DIST_DIR)/$(RELEASE_NAME).tar.gz $(RELEASE_NAME)
	@sha256sum $(DIST_DIR)/$(RELEASE_NAME).tar.gz > $(DIST_DIR)/$(RELEASE_NAME).tar.gz.sha256

release-ready: quality security-test package

eval:
	./scripts/run-eval.sh

eval-stack:
	./scripts/start-eval-stack.sh

clean:
	@rm -rf $(BIN) bin/eval-upstream $(DIST_DIR)
