FROM golang:1.25 AS builder
WORKDIR /src

COPY go.mod ./
COPY go.sum ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/proxy ./cmd/proxy

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/proxy /proxy
EXPOSE 8080
ENTRYPOINT ["/proxy"]
