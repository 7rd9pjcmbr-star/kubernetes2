FROM golang:1.22 AS builder
WORKDIR /src

COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/proxy ./cmd/proxy

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/proxy /proxy
COPY website /static/website
COPY website-v3 /static/website-v3
COPY website-plan /static/website-plan
ENV PROXY_STATIC_ROOT=/static
EXPOSE 8080
ENTRYPOINT ["/proxy"]
