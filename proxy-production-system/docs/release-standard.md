# Proxy Packaging and Standardization Guide

## Versioning

- Use semantic version tags: `vMAJOR.MINOR.PATCH`.
- Build artifacts must embed:
  - `version`
  - `commit`
  - `build_date`

The metadata is exposed at `GET /version` for runtime verification.

## Security validation baseline

Before packaging:

```bash
./scripts/security-test.sh
```

This runs:
- race tests
- `go vet`
- dependency vulnerability scan via `govulncheck`
- Dockerfile runtime policy checks (non-root distroless runtime)

## Packaging baseline

Create release artifact:

```bash
./scripts/package-release.sh v1.0.0
```

Or run one standardized command:

```bash
make release-ready VERSION=v1.0.0
```

Output:
- `dist/proxy-v1.0.0-linux-amd64.tar.gz`
- `dist/proxy-v1.0.0-linux-amd64.tar.gz.sha256`

Tarball includes:
- compiled `proxy` binary
- `README.md`
- deployment manifests
- `BUILD_INFO` metadata file
