#!/usr/bin/env python3
"""Pancake POS HTTP helpers aligned with reverse-mapped connection paths.

Auth modes (from connection_paths_reverse):
- api_key query param (pages.fm / pancake.vn)
- Bearer token (pancake_token | pancake_pos_token)
"""

from __future__ import annotations

import os
from typing import Any

import requests


DEFAULT_BASE_URLS = (
    "https://pos.pages.fm/api/v1",
    "https://pos.pancake.vn/api/v1",
)


def resolve_credentials(
    api_key: str = "",
    access_token: str = "",
) -> dict[str, str]:
    # Match BM config.get_pancake_token() priority, plus POS Open API key aliases.
    centralized = (
        api_key
        or os.getenv("CENTRAL_API_KEY", "")
        or os.getenv("PANCAKE_API_KEY", "")
        or os.getenv("PANCAKE_POS_API_KEY", "")
        or os.getenv("PANCAKE_API_TOKEN", "")
    ).strip()
    token = (
        access_token
        or os.getenv("PANCAKE_POS_ACCESS_TOKEN", "")
        or os.getenv("PANCAKE_POS_TOKEN", "")
        or os.getenv("PANCAKE_TOKEN", "")
        or os.getenv("centralized_api_key_active", "")
        or os.getenv("centralized_api_key", "")
        or os.getenv("pancake_pos_token", "")
        or os.getenv("pancake_token", "")
    ).strip()
    # 32-hex centralized values are POS api_keys; longer/JWT values are bearer tokens.
    if centralized and not token:
        if len(centralized) == 32:
            return {"api_key": centralized, "access_token": ""}
        return {"api_key": "", "access_token": centralized}
    return {"api_key": centralized, "access_token": token}


def auth_ready(creds: dict[str, str]) -> bool:
    return bool(creds.get("api_key") or creds.get("access_token"))


def missing_auth_names(creds: dict[str, str]) -> list[str]:
    if auth_ready(creds):
        return []
    return [
        "PANCAKE_POS_API_KEY",
        "PANCAKE_POS_ACCESS_TOKEN|PANCAKE_POS_TOKEN|PANCAKE_TOKEN",
    ]


def _request_json(
    base_url: str,
    path: str,
    creds: dict[str, str],
    params: dict[str, Any] | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    query = dict(params or {})
    headers = {"Accept": "application/json"}

    if creds.get("api_key"):
        query["api_key"] = creds["api_key"]
    elif creds.get("access_token"):
        headers["Authorization"] = f"Bearer {creds['access_token']}"
    else:
        raise ValueError("Missing Pancake POS credential (api_key or Bearer token).")

    response = requests.get(url, params=query, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected Pancake response type from {url}")
    return payload


def request_json_with_fallback(
    path: str,
    creds: dict[str, str],
    params: dict[str, Any] | None = None,
    base_urls: tuple[str, ...] | list[str] | None = None,
    timeout: int = 20,
) -> tuple[dict[str, Any], str]:
    urls = list(base_urls or DEFAULT_BASE_URLS)
    errors: list[str] = []
    for base in urls:
        try:
            payload = _request_json(base, path, creds, params=params, timeout=timeout)
            return payload, base
        except Exception as exc:
            errors.append(f"{base}: {exc.__class__.__name__}: {exc}")
    raise RuntimeError("Pancake POS request failed on all bases: " + " | ".join(errors))


def fetch_shops(creds: dict[str, str], base_urls=None, timeout: int = 20):
    payload, base = request_json_with_fallback("/shops", creds, base_urls=base_urls, timeout=timeout)
    return payload.get("shops", []), base


def fetch_shop_orders(
    creds: dict[str, str],
    shop_id,
    base_url: str,
    params: dict[str, Any] | None = None,
    timeout: int = 20,
):
    payload = _request_json(
        base_url,
        f"/shops/{shop_id}/orders",
        creds,
        params=params,
        timeout=timeout,
    )
    return payload.get("data", [])
