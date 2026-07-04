BIN := bin/proxy
GO := GOWORK=off go

.PHONY: test test-race vet fmt-check build run quality

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
	GOWORK=off CGO_ENABLED=0 go build -o $(BIN) ./cmd/proxy

run:
	GOWORK=off PROXY_UPSTREAMS=http://localhost:8081,http://localhost:8082 go run ./cmd/proxy

quality: fmt-check test test-race vet build
