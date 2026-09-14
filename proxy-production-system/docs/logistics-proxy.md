# Proxy logistics (J&T Express only)

Phạm vi: **chỉ** đấu nối hệ thống logistics được phép (J&T).

## Upstream trong phạm vi

| Hệ thống | Upstream |
|---|---|
| Ops/CCTV nội bộ | `https://42.115.10.251` |
| HRM logistics (tuỳ chọn) | `https://fast-hrm.jtexpress.vn:8080` |

**Không** cấu hình proxy với tài khoản/URL ngoài logistics (Google, Steam, ngân hàng bên thứ ba, v.v.).

## 1) Tạo cấu hình

```bash
cd proxy-production-system
cp .env.logistics.example .env
```

Mặc định trỏ về `https://42.115.10.251`.

Muốn dùng HRM:

```bash
# trong .env
PROXY_UPSTREAMS=https://fast-hrm.jtexpress.vn:8080
```

> Không round-robin CCTV + HRM chung một process (hai hệ khác nhau).  
> Cần cả hai: chạy 2 instance / 2 port, hoặc đổi `PROXY_UPSTREAMS` theo nhu cầu.

## 2) Đấu nối lại

```bash
./scripts/reconnect-internal.sh
# hoặc
make reconnect-internal
```

Kiểm tra upstream:

```bash
./scripts/reconnect-internal.sh --check-only
```

## 3) Kiểm tra nhanh

```bash
curl -i http://127.0.0.1:8080/healthz
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/config.html
```

HRM (khi đã đổi upstream):

```bash
curl -i http://127.0.0.1:8080/Main/Login.aspx
```

## 4) Secret

Nếu upstream cần Basic Auth của hệ thống logistics **bạn quản lý**:

```bash
# chỉ trong .env local
PROXY_UPSTREAM_BASIC_AUTH=username:password
```

Không commit mật khẩu. Không dán combo list vào repo/chat.

## 5) Kubernetes

```bash
kubectl apply -f deployments/k8s/configmap-logistics.yaml
```

Gắn Deployment `envFrom` sang `proxy-system-config-logistics` khi deploy profile logistics.
