BIN := bin/proxy
GO := GOWORK=off go

.PHONY: test build run

test:
	$(GO) test ./...

build:
	GOWORK=off CGO_ENABLED=0 go build -o $(BIN) ./cmd/proxy

run:
	GOWORK=off PROXY_UPSTREAMS=http://localhost:8081,http://localhost:8082 go run ./cmd/proxy
