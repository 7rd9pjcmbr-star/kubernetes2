# Đánh giá sẵn sàng bán lẻ (Retail Readiness)

**Ngày đánh giá:** 2026-07-19  
**Phiên bản mã nguồn:** `23ac6f54e79`  
**Kết luận:** **CHƯA sẵn sàng bán lẻ.** Đạt mức **MVP / pilot kỹ thuật**, chưa phải sản phẩm retail hoàn chỉnh.

## Kết quả kiểm thử tự động (đã chạy lại)

| Kiểm tra | Kết quả |
|---|---|
| `./scripts/quality-gate.sh` | PASS |
| `./scripts/security-test.sh` (race, vet, govulncheck, Dockerfile policy) | PASS |
| `./scripts/package-release.sh v1.0.0-retail-eval` | PASS (tarball + sha256) |

## Scorecard bán lẻ

| Hạng mục | Mức sẵn sàng | Ghi chú |
|---|---|---|
| Core proxy (round-robin, timeout, graceful shutdown) | Cao | Đủ dùng kỹ thuật |
| Auth cơ bản (token header) | Trung bình | Chỉ token tĩnh, chưa API key lifecycle / JWT / RBAC |
| Rate limiting | Trung bình | Theo IP local process, chưa phân tán theo cluster |
| Observability (metrics/logs/traces) | Cao | Có `/metrics`, JSON log, OTLP |
| Quality gate / unit+integration test | Cao | Có race/vet/integration |
| Packaging | Trung bình | Có tarball + checksum, chưa ký artifact / SBOM |
| Kubernetes deploy baseline | Trung bình | Có Deployment/Service/HPA/Ingress |
| TLS / HTTPS production | Thấp | Ingress chưa có `tls`, image vẫn `:latest` |
| Hardening K8s | Thấp | Thiếu PDB, NetworkPolicy, Secret chuẩn |
| Admin UI / portal khách | Không có | Cần cho bán lẻ self-serve |
| Multi-tenant / quota / billing | Không có | Cần nếu bán SaaS/retail |
| License / EULA / SLA thương mại | Không có | Chưa có gói pháp lý bàn giao |
| Load/SLO nghiệm thu | Thấp | Chưa có báo cáo p95/p99 + error budget |
| Brand / registry sản phẩm | Thấp | Image placeholder `ghcr.io/example/...` |

## Đã có (đủ cho demo / pilot nội bộ)

- Reverse proxy round-robin
- Auth token, rate limit, request timeout
- Health/ready/metrics/version
- Structured logging + tracing
- Quality/security gate + release packaging
- Docs: quickstart, user-guide, release checklist
- NGINX Ingress baseline

## Chưa đủ để bán lẻ (blocker)

1. **TLS bắt buộc + secret management thật** (không để token trong ConfigMap).
2. **Image immutable** (cấm `latest` trên production).
3. **PDB + NetworkPolicy + rollback runbook đã kiểm chứng**.
4. **Load/SLO test có số liệu** trước nghiệm thu khách.
5. **Ký artifact + SBOM** (cosign/syft hoặc tương đương).
6. **Gói sản phẩm bán lẻ:** license/EULA, hỗ trợ, versioning thương mại, branding registry.
7. Nếu bán SaaS: **multi-tenant, quota, billing, admin portal**.

## Nghiệm thu ngay trên máy

Trước khi bán, chạy đánh giá kỹ thuật:

```bash
./scripts/run-eval.sh
```

Hoặc giữ stack để tự thử tay:

```bash
./scripts/start-eval-stack.sh
```

Xem `docs/eval-guide.md`.

## Phân loại sử dụng hiện tại

| Mục đích | Có nên dùng? |
|---|---|
| Demo / PoC nội bộ | Có |
| Pilot 1 khách kỹ thuật (có hỗ trợ kỹ sư) | Có, có điều kiện |
| Bán lẻ self-serve / marketplace | **Không** |
| Bàn giao enterprise không người hỗ trợ | **Không** |

## Ngưỡng “đủ bán lẻ tối thiểu” (Go / No-Go)

Chỉ chuyển sang **Go bán lẻ** khi hoàn thành blocker #1–#6 ở trên và:
- Staging chạy ổn định với traffic thật hoặc tương đương.
- Checklist `docs/release-checklist.md` tick đủ.
- Có phiên bản semver thương mại (ví dụ `v1.0.0`) + artifact đã ký.
