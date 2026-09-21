BIN := bin/proxy
BOT_BIN := bin/tondaithanh-bot
GO := GOWORK=off go

.PHONY: test build build-bot run run-bot python-deps env-check

python-deps:
	python3 -m pip install -r requirements.txt
	python3 -m playwright install chromium

env-check:
	python3 scripts/load_env.py --check

test:
	$(GO) test ./...

build:
	GOWORK=off CGO_ENABLED=0 go build -o $(BIN) ./cmd/proxy

build-bot:
	GOWORK=off CGO_ENABLED=0 go build -o $(BOT_BIN) ./cmd/tondaithanh-bot

run:
	GOWORK=off PROXY_UPSTREAMS=http://localhost:8081,http://localhost:8082 go run ./cmd/proxy

run-bot:
	GOWORK=off go run ./cmd/tondaithanh-bot
