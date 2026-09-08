# -*- coding: utf-8 -*-
"""J&T Vietnam order extractor — standalone, reads configs/config_jt.json only."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from vps_utils import (
    build_requests_proxy,
    is_vps_environment,
    load_proxy_pool,
    pick_user_agent,
    resolve_account_proxy,
    sleep_between_accounts,
    with_retries,
)

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT_DIR / "configs" / "config_jt.json"

BAC_BO = [
    "hà nội", "hải phòng", "hải dương", "hưng yên", "bắc ninh", "bắc giang",
    "lạng sơn", "cao bằng", "bắc kạn", "tuyên quang", "hà giang", "lào cai",
    "yên bái", "điện biên", "hòa bình", "lai châu", "sơn la", "phú thọ",
    "vĩnh phúc", "quảng ninh", "thái nguyên", "thái bình", "nam định",
    "hà nam", "ninh bình",
]
TRUNG_BO = [
    "thanh hóa", "nghệ an", "hà tĩnh", "quảng bình", "quảng trị",
    "thừa thiên huế", "huế", "đà nẵng", "quảng nam", "quảng ngãi",
    "bình định", "phú yên", "khánh hòa", "nha trang", "ninh thuận",
    "bình thuận", "kon tum", "gia lai", "đắc lắc", "đắk lắk", "đắc nông",
    "đắk nông", "lâm đồng", "đà lạt",
]
NAM_BO = [
    "hồ chí minh", "hcm", "sài gòn", "bình dương", "đồng nai", "bà rịa",
    "vũng tàu", "long an", "tiền giang", "bến tre", "trà vinh", "vĩnh long",
    "đồng tháp", "an giang", "kiên giang", "cần thơ", "hậu giang", "sóc trăng",
    "bạc liêu", "cà mau", "tây ninh", "bình phước",
]

COLUMNS_ORDER = [
    "vùng miền", "tên shop", "mã vận đơn", "đơn vị vận chuyển", "tên khách",
    "số điện thoại", "địa chỉ nhận hàng", "sản phẩm", "số lượng", "tổng tiền",
    "trạng thái", "cod", "ngày cập nhật",
]


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy config: {path}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    accounts = data.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("config_jt.json phải có danh sách 'accounts' không rỗng")
    return data


def detect_region_from_address(address_str: str) -> str:
    if not address_str or address_str == "N/A":
        return "Không rõ"
    addr_lower = address_str.lower()
    for tinh in NAM_BO:
        if tinh in addr_lower:
            return "Miền Nam"
    for tinh in BAC_BO:
        if tinh in addr_lower:
            return "Miền Bắc"
    for tinh in TRUNG_BO:
        if tinh in addr_lower:
            return "Miền Trung"
    return "Khác/Chưa rõ"


def clean_latin1_string(input_str: Any) -> str:
    if not input_str:
        return ""
    cleaned = str(input_str).replace("\ufeff", "").strip()
    return "".join(c for c in cleaned if ord(c) < 256)


def extract_and_filter_jtexpress_cookies(file_path: Path) -> str:
    if not file_path.exists():
        print(f"[-] Không tìm thấy file Excel cookie tại {file_path}")
        return ""
    try:
        df = pd.read_excel(file_path)
        cookie_pairs: list[str] = []
        col_name, col_value = None, None

        for col in df.columns:
            col_str = str(col).lower()
            if col_str in ["name", "key", "tên", "cookie name"]:
                col_name = col
            if col_str in ["value", "giá trị", "cookie value"]:
                col_value = col

        if not col_name or not col_value:
            col_name = df.columns[-2] if len(df.columns) >= 2 else df.columns[0]
            col_value = df.columns[-1]

        for _, row in df.iterrows():
            c_name = str(row[col_name]).strip()
            c_value = str(row[col_value]).strip()
            if not c_name or not c_value or c_name == "nan" or c_value == "nan":
                continue
            c_name_clean = clean_latin1_string(c_name)
            c_value_clean = clean_latin1_string(c_value)
            if c_name_clean in ["PHPSESSID", "user_auth"]:
                cookie_pairs.append(f"{c_name_clean}={c_value_clean}")

        return "; ".join(cookie_pairs)
    except Exception as exc:
        print(f"[-] Lỗi lọc cookie từ Excel: {exc}")
        return ""


def cookies_from_config(account: dict[str, Any]) -> str:
    cookies_cfg = account.get("cookies") or {}
    if isinstance(cookies_cfg, dict):
        pairs = []
        for key in ("PHPSESSID", "user_auth"):
            value = clean_latin1_string(cookies_cfg.get(key, ""))
            if value:
                pairs.append(f"{key}={value}")
        if pairs:
            return "; ".join(pairs)

    cookie_excel = str(account.get("cookie_excel", "")).strip()
    if cookie_excel:
        excel_path = Path(cookie_excel)
        if not excel_path.is_absolute():
            excel_path = ROOT_DIR / excel_path
        return extract_and_filter_jtexpress_cookies(excel_path)

    return ""


def fetch_orders_for_account(
    account: dict[str, Any],
    settings: dict[str, Any],
    proxy_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    shop_name = str(account.get("username", "")).strip() or "Tài khoản J&T"
    cookie_header = cookies_from_config(account)
    if not cookie_header:
        print(
            f"[-] {shop_name}: thiếu cookie. Điền cookies.PHPSESSID/user_auth "
            "hoặc cookie_excel trong config_jt.json."
        )
        return []

    print(f"[+] {shop_name}: đã cô lập session cookie cốt lõi.")

    days_back = int(settings.get("days_back", 3))
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    timeout = int(settings.get("request_timeout_seconds", 20))
    api_url = str(settings.get("api_url", "https://jtexpress.vn")).strip()

    headers = {
        "User-Agent": pick_user_agent(settings),
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://vip.jtexpress.vn",
        "Referer": "https://vip.jtexpress.vn/",
        "Connection": "close",
        "Cookie": cookie_header,
    }

    payload = {
        "start_date": start_date.strftime("%Y-%m-%d 00:00:00"),
        "end_date": end_date.strftime("%Y-%m-%d 23:59:59"),
        "page": 1,
        "limit": int(settings.get("page_limit", 250)),
        "status": str(settings.get("order_status", "IN_TRANSIT")),
    }

    proxies = build_requests_proxy(proxy_cfg)
    if is_vps_environment() and not proxies:
        print(f"[!] {shop_name}: VPS không dùng proxy — rủi ro bị chặn cao.")
    print(f"[*] {shop_name}: kết nối tới {api_url}...")

    extracted: list[dict[str, Any]] = []
    try:
        def _post_once() -> requests.Response:
            return requests.post(
                api_url,
                json=payload,
                headers=headers,
                proxies=proxies,
                timeout=timeout,
            )

        response = with_retries(
            _post_once,
            settings=settings,
            label=f"J&T API {shop_name}",
            retryable_status=lambda resp: resp.status_code in (429, 502, 503, 504),
        )

        if response.status_code != 200:
            print(f"[-] {shop_name}: máy chủ trả mã {response.status_code}")
            if response.status_code in (401, 403):
                print(
                    "[!] Phiên cookie có thể đã hết hạn — login lại web J&T "
                    "và cập nhật config."
                )
            return extracted

        api_data = response.json()
        data_records = (
            api_data.get("data", {}).get("records", [])
            or api_data.get("data", [])
            or []
        )
        if isinstance(data_records, dict):
            data_records = data_records.get("list", [])

        for item in data_records:
            status_name = (
                item.get("status_name") or item.get("status") or "Đang giao hàng"
            )
            address = item.get("receiver_address") or item.get("address") or "N/A"
            extracted.append({
                "vùng miền": detect_region_from_address(address),
                "tên shop": shop_name,
                "mã vận đơn": item.get("bill_code") or item.get("waybill_no") or "N/A",
                "đơn vị vận chuyển": "J&T Express VN",
                "tên khách": item.get("receiver_name") or "N/A",
                "số điện thoại": item.get("receiver_phone") or "N/A",
                "địa chỉ nhận hàng": address,
                "sản phẩm": item.get("items_name") or item.get("goods_name") or "Hàng hóa",
                "số lượng": str(item.get("total_qty") or item.get("qty") or 1),
                "tổng tiền": item.get("goods_value") or item.get("total_amount") or 0,
                "trạng thái": status_name,
                "cod": item.get("cod_amount") or item.get("cod") or 0,
                "ngày cập nhật": item.get("updated_at") or item.get("create_time") or "N/A",
            })

        print(f"[+] {shop_name}: lấy được {len(extracted)} đơn đang giao.")
    except Exception as exc:
        print(f"[-] {shop_name}: lỗi kết nối — {exc}")

    return extracted


def resolve_output_path(settings: dict[str, Any]) -> Path:
    output_excel = str(settings.get("output_excel", "outputs/báo_cáo_đơn_đang_giao.xlsx"))
    output_path = Path(output_excel)
    if not output_path.is_absolute():
        output_path = ROOT_DIR / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def run_jtexpress_vn_extraction() -> int:
    try:
        config = load_config()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[-] Lỗi config: {exc}", file=sys.stderr)
        return 2

    settings = config.get("settings", {})
    proxy_pool = load_proxy_pool(config)
    all_orders: list[dict[str, Any]] = []

    for index, account in enumerate(config["accounts"], start=1):
        if index > 1:
            sleep_between_accounts(settings)
        label = str(account.get("username") or f"account_{index}")
        print(f"\n=== Tài khoản {index}/{len(config['accounts'])}: {label} ===")
        proxy_cfg = resolve_account_proxy(account, index - 1, proxy_pool, settings)
        all_orders.extend(fetch_orders_for_account(account, settings, proxy_cfg))

    if not all_orders:
        print(
            "\n[-] Không lấy được dữ liệu. Kiểm tra cookie/proxy trong config_jt.json."
        )
        return 1

    output_path = resolve_output_path(settings)
    df = pd.DataFrame(all_orders)[COLUMNS_ORDER]
    df.to_excel(output_path, index=False, sheet_name="J&T Đang Giao")
    print(
        f"\n[===== HOÀN THÀNH =====] File Excel: {output_path} "
        f"({len(all_orders)} đơn)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_jtexpress_vn_extraction())
