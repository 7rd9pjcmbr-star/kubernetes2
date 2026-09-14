FROM golang:1.22 AS builder
WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/proxy ./cmd/proxy
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/tondaithanh-bot ./cmd/tondaithanh-bot

FROM gcr.io/distroless/static-debian12:nonroot AS proxy
COPY --from=builder /out/proxy /proxy
COPY website /static/website
COPY website-v3 /static/website-v3
ENV PROXY_STATIC_ROOT=/static
EXPOSE 8080
ENTRYPOINT ["/proxy"]

FROM gcr.io/distroless/static-debian12:nonroot AS bot
COPY --from=builder /out/tondaithanh-bot /tondaithanh-bot
ENTRYPOINT ["/tondaithanh-bot"]
