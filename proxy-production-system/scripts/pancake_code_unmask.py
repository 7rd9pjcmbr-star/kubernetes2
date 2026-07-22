#!/usr/bin/env python3
"""Đổi OAuth code → session/token để giải che PII (hỗ trợ đặc biệt).

Pancake POS login trả `code` về:
  https://pancake.vn/api/v1/users/pancake_id_login_success?code=...&state=...

Endpoint đó (GET) đổi code phía server và gắn session. Script này:
  1) parse callback / raw code
  2) gọi exchange, bắt Set-Cookie / token trong body
  3) ghi local env (không commit)
  4) probe đơn hàng: còn mask hay đã giải che

Usage:
  # Sau khi login, dán full callback URL (có code=)
  python3 pancake_code_unmask.py --callback-url 'https://pancake.vn/api/v1/users/pancake_id_login_success?code=...&state=...'

  # Hoặc chỉ code (+ state từ login POS)
  python3 pancake_code_unmask.py --code YOUR_CODE --require-pos-login

  # Đã có cookie từ DevTools → chỉ lưu + probe
  python3 pancake_code_unmask.py --cookie 'token=...; ...' --probe

  # Chỉ in curl / báo cáo, không gọi mạng
  python3 pancake_code_unmask.py --callback-url '...' --dry-run
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

ASUNMEE_ENV = Path(os.getenv("PANCAKE_ENV_FILE", "/home/ubuntu/.config/scantool/asunmee.env"))
DEFAULT_CLIENT_ID = "53e2d5e33a8940f4a30ba22a4011e52a"
DEFAULT_EXCHANGE = "https://pancake.vn/api/v1/users/pancake_id_login_success"
DEFAULT_SHOP = "714934229"
DEFAULT_BASE = "https://pos.pages.fm/api/v1"
POS_STATE = {"country": "VN", "pos_login": True, "hostname": "pos.pancake.vn"}


def load_extra_env() -> None:
    for path in (ASUNMEE_ENV, Path(__file__).resolve().parent / ".env.vn-platforms"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def mask(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return value[:keep] + "..." + value[-keep:]


def decode_state(raw_state: str):
    if not raw_state:
        return None, "missing_state"
    try:
        padding = "=" * ((4 - len(raw_state) % 4) % 4)
        decoded = base64.b64decode((raw_state + padding).encode("utf-8")).decode("utf-8")
        obj = json.loads(decoded)
        if isinstance(obj, dict):
            return obj, None
        return None, "state_not_object"
    except Exception as exc:  # noqa: BLE001 — surface decode reason to user
        return None, f"state_decode_error: {exc}"


def encode_pos_state() -> str:
    raw = json.dumps(POS_STATE, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    order: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key not in existing:
                order.append(key)
            existing[key] = value
    for key, value in updates.items():
        if key not in existing:
            order.append(key)
        existing[key] = value
    body = "\n".join(f"{k}={existing[k]}" for k in order) + "\n"
    path.write_text(body, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def parse_set_cookie(headers) -> str:
    """Join Set-Cookie name=value pairs into a Cookie request header."""
    raw_list = []
    if hasattr(headers, "get_list"):
        raw_list = headers.get_list("Set-Cookie") or []
    if not raw_list:
        # requests stores only the last Set-Cookie; also check urllib3
        single = headers.get("Set-Cookie")
        if single:
            raw_list = [single]
    pairs = []
    for item in raw_list:
        part = item.split(";", 1)[0].strip()
        if part and "=" in part:
            pairs.append(part)
    # Prefer token-like cookies first for readability, keep all.
    return "; ".join(pairs)


def extract_tokens_from_payload(payload) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(payload, dict):
        return out
    for key in (
        "access_token",
        "accessToken",
        "token",
        "refresh_token",
        "refreshToken",
    ):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    nested = payload.get("data")
    if isinstance(nested, dict):
        for key, val in extract_tokens_from_payload(nested).items():
            out.setdefault(key, val)
    return out


def build_exchange_url(args, code: str, state: str, client_id: str) -> str:
    base = args.exchange_url.rstrip("/")
    params = {
        "code": code,
        "client_id": client_id,
        "redirect_uri": args.redirect_uri,
    }
    if state:
        params["state"] = state
    return base + "?" + urllib.parse.urlencode(params)


def exchange_code(args, code: str, state: str, client_id: str) -> dict:
    url = build_exchange_url(args, code, state, client_id)
    session = requests.Session()
    session.trust_env = False  # avoid exhausted DataImpulse proxy
    headers = {
        "Accept": "application/json, text/html, */*",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://account.pancake.vn/",
    }
    # Do not follow redirects automatically — capture intermediate cookies.
    resp = session.get(url, headers=headers, allow_redirects=False, timeout=30)
    cookie = parse_set_cookie(resp.headers)
    location = resp.headers.get("Location", "")
    payload = None
    text = resp.text or ""
    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        payload = None

    # Follow one hop if redirect (POS hostname) and merge cookies.
    hop_status = None
    hop_url = None
    if location and resp.status_code in (301, 302, 303, 307, 308):
        hop_url = urllib.parse.urljoin(url, location)
        hop = session.get(hop_url, headers=headers, allow_redirects=False, timeout=30)
        hop_status = hop.status_code
        more = parse_set_cookie(hop.headers)
        if more:
            cookie = "; ".join(x for x in (cookie, more) if x)
        if not payload:
            try:
                payload = hop.json()
            except Exception:  # noqa: BLE001
                pass

    # Also collect session cookies jar (covers multi Set-Cookie).
    jar_pairs = [f"{c.name}={c.value}" for c in session.cookies]
    if jar_pairs:
        # Merge unique by cookie name (jar wins).
        by_name: dict[str, str] = {}
        for part in (cookie.split(";") if cookie else []):
            part = part.strip()
            if "=" in part:
                n, v = part.split("=", 1)
                by_name[n.strip()] = v.strip()
        for part in jar_pairs:
            n, v = part.split("=", 1)
            by_name[n] = v
        cookie = "; ".join(f"{k}={v}" for k, v in by_name.items())

    tokens = extract_tokens_from_payload(payload) if isinstance(payload, dict) else {}
    # Heuristic: JWT-looking cookie value named token / access_token
    if cookie and "access_token" not in tokens:
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith("token=") or part.startswith("access_token="):
                tokens.setdefault("token", part.split("=", 1)[1])

    ok = resp.status_code < 400 and bool(cookie or tokens)
    error = None
    if not ok:
        if isinstance(payload, str):
            error = payload
        elif isinstance(payload, dict):
            error = payload.get("message") or payload.get("error") or json.dumps(payload)[:200]
        else:
            error = text[:200] or f"http_{resp.status_code}"

    return {
        "ok": ok,
        "http_status": resp.status_code,
        "exchange_url_preview": re.sub(r"code=[^&]+", "code=***", url),
        "location": location,
        "hop_status": hop_status,
        "hop_url": hop_url,
        "cookie": cookie,
        "cookie_preview": mask(cookie, keep=6) if cookie else "",
        "tokens": {k: mask(v, keep=6) for k, v in tokens.items()},
        "tokens_raw": tokens,
        "payload_type": type(payload).__name__,
        "error": error,
    }


def probe_unmask(cookie: str = "", access_token: str = "", api_key: str = "", shop_id: str = DEFAULT_SHOP) -> dict:
    url = f"{os.getenv('PANCAKE_POS_BASE_URL', DEFAULT_BASE).rstrip('/')}/shops/{shop_id}/orders"
    headers = {
        "Accept": "application/json",
        "Origin": "https://pos.pancake.vn",
        "Referer": f"https://pos.pancake.vn/shop/{shop_id}/order",
    }
    params: dict[str, str | int] = {"limit": 5, "page_number": 1, "page": 1}
    auth_mode = []
    if cookie:
        headers["Cookie"] = cookie
        auth_mode.append("cookie")
    if access_token:
        params["access_token"] = access_token
        headers["Authorization"] = f"Bearer {access_token}"
        auth_mode.append("access_token")
    if api_key:
        params["api_key"] = api_key
        auth_mode.append("api_key")
    if not auth_mode:
        return {"ok": False, "error": "no_auth", "auth_mode": []}

    session = requests.Session()
    session.trust_env = False
    resp = session.get(url, params=params, headers=headers, timeout=30)
    try:
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return {
            "ok": False,
            "http_status": resp.status_code,
            "auth_mode": auth_mode,
            "error": (resp.text or "")[:200],
        }
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        rows = []
    sample = []
    masked = 0
    clear = 0
    for order in rows[:5]:
        if not isinstance(order, dict):
            continue
        customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
        ship = order.get("shipping_address") if isinstance(order.get("shipping_address"), dict) else {}
        name = str(order.get("bill_full_name") or ship.get("full_name") or customer.get("name") or "")
        phone = str(order.get("bill_phone_number") or ship.get("phone_number") or "")
        is_masked = ("*" in name) or ("*" in phone)
        if is_masked:
            masked += 1
        elif name or phone:
            clear += 1
        sample.append(
            {
                "id": order.get("id"),
                "name": name if is_masked else mask(name, keep=2),
                "phone": phone if is_masked else mask(phone, keep=2),
                "is_masked": is_masked,
            }
        )
    return {
        "ok": resp.status_code < 400 and payload.get("success") is not False,
        "http_status": resp.status_code,
        "auth_mode": auth_mode,
        "orders_sampled": len(sample),
        "masked_count": masked,
        "clear_count": clear,
        "unmask_ready": clear > 0 and masked == 0,
        "still_masked": masked > 0 and clear == 0,
        "sample": sample,
        "api_message": payload.get("message") if isinstance(payload, dict) else None,
    }


def parse_args():
    load_extra_env()
    p = argparse.ArgumentParser(
        description="Đổi Pancake OAuth code → cookie/token và probe giải che PII."
    )
    p.add_argument("--callback-url", default="", help="Full redirect URL chứa code=...&state=...")
    p.add_argument("--code", default="", help="Authorization code (nếu không có callback URL)")
    p.add_argument("--state", default="", help="State base64; mặc định state POS VN nếu --code")
    p.add_argument("--client-id", default=os.getenv("PANCAKE_OAUTH_CLIENT_ID", DEFAULT_CLIENT_ID))
    p.add_argument(
        "--redirect-uri",
        default="https://pancake.vn/api/v1/users/pancake_id_login_success",
    )
    p.add_argument(
        "--exchange-url",
        default=DEFAULT_EXCHANGE,
        help="Endpoint đổi code (GET). Mặc định pancake_id_login_success.",
    )
    p.add_argument("--cookie", default="", help="Cookie POS sẵn có (bỏ qua exchange)")
    p.add_argument("--access-token", default="", help="access_token sẵn có")
    p.add_argument("--require-pos-login", action="store_true", help="Bắt buộc state.pos_login=true")
    p.add_argument("--dry-run", action="store_true", help="Chỉ parse / in URL, không gọi exchange")
    p.add_argument("--no-save", action="store_true", help="Không ghi ~/.config/scantool/asunmee.env")
    p.add_argument("--probe", action="store_true", default=True, help="Probe giải che sau khi lưu (mặc định)")
    p.add_argument("--no-probe", action="store_true", help="Bỏ probe")
    p.add_argument("--shop-id", default=os.getenv("PANCAKE_POS_SHOP_IDS", DEFAULT_SHOP).split(",")[0].strip())
    p.add_argument("--env-file", default=str(ASUNMEE_ENV))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    do_probe = args.probe and not args.no_probe
    env_path = Path(args.env_file)

    code = args.code.strip()
    state = args.state.strip()
    client_id = args.client_id.strip() or DEFAULT_CLIENT_ID
    cookie = args.cookie.strip() or os.getenv("PANCAKE_POS_COOKIE", "").strip()
    access_token = args.access_token.strip() or os.getenv("PANCAKE_POS_ACCESS_TOKEN", "").strip()

    state_obj = None
    state_error = None
    if args.callback_url:
        parsed = urllib.parse.urlparse(args.callback_url)
        query = urllib.parse.parse_qs(parsed.query)
        code = code or (query.get("code") or [""])[0]
        state = state or (query.get("state") or [""])[0]
        client_id = (query.get("client_id") or [client_id])[0] or client_id

    if state:
        state_obj, state_error = decode_state(state)
    elif code and not cookie:
        state = encode_pos_state()
        state_obj, state_error = decode_state(state)

    if args.require_pos_login:
        if not state_obj or state_obj.get("pos_login") is not True:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "state_pos_login_required",
                        "state_decoded": state_obj,
                        "state_error": state_error,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1

    report: dict = {
        "purpose": "disability_unmask_code_exchange",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_present": bool(code),
        "code_preview": mask(code, keep=3) if code else "",
        "client_id": client_id,
        "state_valid_json": state_error is None if state else None,
        "state_error": state_error,
        "state_decoded": state_obj,
        "env_file": str(env_path),
    }

    if cookie and not code:
        report["mode"] = "cookie_direct"
    elif code:
        report["mode"] = "oauth_code_exchange"
        if args.dry_run:
            preview = build_exchange_url(args, code, state, client_id)
            report["dry_run"] = True
            report["exchange_get"] = re.sub(r"code=[^&]+", "code=***", preview)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print("\n# Đổi code (GET — endpoint thật của Pancake POS):")
            print(f"curl -sS -D - -o /tmp/pancake_exchange.body '{preview}'")
            return 0
        exchanged = exchange_code(args, code, state, client_id)
        report["exchange"] = {k: v for k, v in exchanged.items() if k != "tokens_raw"}
        if exchanged.get("cookie"):
            cookie = exchanged["cookie"]
        tokens_raw = exchanged.get("tokens_raw") or {}
        access_token = (
            tokens_raw.get("access_token")
            or tokens_raw.get("accessToken")
            or tokens_raw.get("token")
            or access_token
        )
        if not exchanged.get("ok") and not cookie and not access_token:
            report["ok"] = False
            report["hint"] = (
                "Code hết hạn/đã dùng, hoặc login chưa xong. "
                "Mở lại URL login → copy callback có code= mới. "
                "Hoặc dán Cookie từ DevTools: Application → Cookies → pos.pancake.vn"
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2
    else:
        report["ok"] = False
        report["error"] = "need_callback_or_code_or_cookie"
        report["login_url"] = (
            "https://account.pancake.vn/login?"
            + urllib.parse.urlencode(
                {
                    "client_id": client_id,
                    "grant_type": "code",
                    "locale": "vi",
                    "redirect_uri": args.redirect_uri,
                    "scope": "avatar,email,subscriptions",
                    "state": encode_pos_state(),
                    "verification_method": "email",
                }
            )
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    saved = {}
    if not args.no_save and (cookie or access_token):
        updates = {}
        if cookie:
            updates["PANCAKE_POS_COOKIE"] = cookie
        if access_token:
            updates["PANCAKE_POS_ACCESS_TOKEN"] = access_token
            updates["PANCAKE_POS_TOKEN"] = access_token
        upsert_env(env_path, updates)
        saved = {k: mask(v, keep=6) for k, v in updates.items()}
        report["saved"] = saved

    if do_probe:
        api_key = os.getenv("PANCAKE_POS_API_KEY", "").strip()
        # Prefer session cookie for unmask; api_key alone stays masked.
        report["probe"] = probe_unmask(
            cookie=cookie,
            access_token=access_token if not cookie else "",
            api_key=api_key if not (cookie or access_token) else "",
            shop_id=args.shop_id,
        )

    report["ok"] = bool(cookie or access_token)
    report["next"] = []
    if report.get("probe", {}).get("unmask_ready"):
        report["next"].append("PII đã rõ — chạy: python3 scripts/speak_orders_accessibility.py --days 7 --telegram")
    elif report.get("probe", {}).get("still_masked"):
        report["next"].append(
            "Vẫn mask: cookie/token chưa đủ quyền session POS. "
            "Dán pancake_a11y_unmask_hook.js trên tab đã login, hoặc copy Cookie mới."
        )
    else:
        report["next"].append("python3 scripts/fetch_unmasked_orders.py --days 1")
        report["next"].append("Alt+Shift+S trên tab POS (pancake_a11y_unmask_hook.js)")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
