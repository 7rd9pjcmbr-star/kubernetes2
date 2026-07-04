FROM golang:1.25 AS builder
WORKDIR /src
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown

COPY go.mod ./
COPY go.sum ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags "-X proxy-production-system/internal/buildinfo.Version=${VERSION} -X proxy-production-system/internal/buildinfo.Commit=${COMMIT} -X proxy-production-system/internal/buildinfo.BuildDate=${BUILD_DATE}" \
    -o /out/proxy ./cmd/proxy

FROM gcr.io/distroless/static-debian12:nonroot
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="proxy-production-system"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.revision="${COMMIT}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
COPY --from=builder /out/proxy /proxy
EXPOSE 8080
ENTRYPOINT ["/proxy"]
