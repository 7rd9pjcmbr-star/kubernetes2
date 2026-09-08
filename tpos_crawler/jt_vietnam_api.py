#!/usr/bin/env python3
"""J&T Vietnam order fetcher — standalone, reads configs/config_jt.json only."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT_DIR / "configs" / "config_jt.json"
JT_PASSWORD_SUFFIX = "jadada369t3"
JT_OPEN_API_BASE = "https://ylopenapi.jtexpress.vn/webopenplatformapi/api"


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    accounts = data.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("config_jt.json must contain a non-empty 'accounts' list")
    return data


def build_proxy_url(proxy_cfg: dict[str, Any]) -> str | None:
    if not proxy_cfg.get("enabled"):
        return None
    host = str(proxy_cfg.get("host", "")).strip()
    port = proxy_cfg.get("port")
    if not host or not port:
        return None
    scheme = str(proxy_cfg.get("scheme", "http")).strip() or "http"
    username = str(proxy_cfg.get("username", "")).strip()
    password = str(proxy_cfg.get("password", "")).strip()
    if username:
        auth = f"{username}:{password}@"
        return f"{scheme}://{auth}{host}:{port}"
    return f"{scheme}://{host}:{port}"


def make_session(proxy_cfg: dict[str, Any], timeout: int) -> tuple[requests.Session, int]:
    session = requests.Session()
    session.headers.update({"User-Agent": "tpos_crawler/jt_vietnam_api"})
    proxy_url = build_proxy_url(proxy_cfg)
    if proxy_url:
        session.proxies.update({"http": proxy_url, "https": proxy_url})
    return session, timeout


def jt_business_password(plain_password: str) -> str:
    payload = f"{plain_password}{JT_PASSWORD_SUFFIX}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest().upper()


def jt_header_digest(biz_content: str, private_key: str) -> str:
    raw = hashlib.md5(f"{biz_content}{private_key}".encode("utf-8")).digest()
    return base64.b64encode(raw).decode("ascii")


def fetch_orders_for_account(
    account: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    username = str(account.get("username", "")).strip()
    password = str(account.get("password", "")).strip()
    if not username or not password:
        raise ValueError("Each account needs non-empty username and password")

    api_account = str(account.get("api_account", username)).strip()
    private_key = str(account.get("private_key", "")).strip()
    customer_code = str(account.get("customer_code", username)).strip()
    timeout = int(settings.get("request_timeout_seconds", 30))

    session, timeout = make_session(account.get("proxy", {}), timeout)

    if not private_key:
        return {
            "account": username,
            "mode": "credentials_only",
            "status": "skipped",
            "message": "Set api_account/private_key/customer_code in config for Open API order fetch.",
        }

    biz_payload = {
        "customerCode": customer_code,
        "password": jt_business_password(password),
        "current": 1,
        "size": 50,
    }
    biz_content = json.dumps(biz_payload, ensure_ascii=False, separators=(",", ":"))
    headers = {
        "apiAccount": api_account,
        "digest": jt_header_digest(biz_content, private_key),
        "timestamp": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    response = session.post(
        f"{JT_OPEN_API_BASE}/order/getOrders",
        data={"bizContent": biz_content},
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "account": username,
        "mode": "open_api",
        "status": "ok",
        "orders": payload,
    }


def save_results(results: list[dict[str, Any]], settings: dict[str, Any]) -> Path:
    output_dir = ROOT_DIR / str(settings.get("output_dir", "output/jt"))
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"jt_orders_{stamp}.json"
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def main() -> int:
    try:
        config = load_config()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"jt_vietnam_api: {exc}", file=sys.stderr)
        return 2

    settings = config.get("settings", {})
    results: list[dict[str, Any]] = []
    for index, account in enumerate(config["accounts"], start=1):
        label = str(account.get("username") or f"account_{index}")
        print(f"[{index}/{len(config['accounts'])}] J&T account: {label}")
        try:
            results.append(fetch_orders_for_account(account, settings))
        except requests.RequestException as exc:
            print(f"  request failed: {exc}", file=sys.stderr)
            results.append({"account": label, "status": "error", "error": str(exc)})
        except ValueError as exc:
            print(f"  invalid account config: {exc}", file=sys.stderr)
            results.append({"account": label, "status": "error", "error": str(exc)})

    output_path = save_results(results, settings)
    print(f"Saved results to {output_path}")
    return 0 if any(item.get("status") == "ok" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
