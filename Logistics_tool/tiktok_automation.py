# -*- coding: utf-8 -*-
"""TPOS order automation — standalone, reads configs/config_tiktok.json only."""

from __future__ import annotations

import json
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from playwright.sync_api import BrowserContext, sync_playwright

from vps_utils import (
    anti_block_settings,
    apply_stealth_init_script,
    browser_context_options,
    build_playwright_proxy,
    is_vps_environment,
    load_proxy_pool,
    resolve_account_proxy,
    resolve_headless,
    sleep_between_accounts,
    STEALTH_LAUNCH_ARGS,
)

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT_DIR / "configs" / "config_tiktok.json"

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
    "bình thuận", "kon tum", "gia lai", "đắk lắk", "đắc lắc", "đắk nông",
    "đắc nông", "lâm đồng", "đà lạt",
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
        raise ValueError("config_tiktok.json phải có danh sách 'accounts' không rỗng")
    return data


def normalize_shop_name(raw_shop: str) -> str:
    shop = raw_shop.strip().replace("https://", "").replace("http://", "")
    return shop.split(".")[0]


def parse_account(account: dict[str, Any]) -> tuple[str, str, str] | None:
    shop_raw = str(account.get("shop", "")).strip()
    username = str(account.get("username", "")).strip()
    password = str(account.get("password", "")).strip()
    if not shop_raw or not username or not password:
        return None
    return normalize_shop_name(shop_raw), username, password


def try_reuse_session(
    shop_name: str,
    session_dir: Path,
    settings: dict[str, Any],
    all_orders: list[dict[str, Any]],
    playwright_instance: Any,
    proxy_config: dict[str, str] | None,
) -> bool:
    ab = anti_block_settings(settings)
    if not ab.get("reuse_tpos_session"):
        return False

    session_file = session_dir / f"{shop_name}_session.json"
    if not session_file.exists():
        return False

    print(f"[*] Thử tái sử dụng session đã lưu: {session_file.name}")
    headless = resolve_headless(settings)
    browser = playwright_instance.chromium.launch(
        headless=headless,
        proxy=proxy_config,
        args=STEALTH_LAUNCH_ARGS,
    )
    context = browser.new_context(
        storage_state=str(session_file),
        **browser_context_options(settings),
    )
    page = context.new_page()
    apply_stealth_init_script(page)
    try:
        page.goto(f"https://{shop_name}.tpos.vn/#/desktop", timeout=20000)
        if "login" in page.url:
            print(f"[-] Session {shop_name} đã hết hạn, sẽ login lại.")
            return False
        before = len(all_orders)
        fetch_and_parse_orders(shop_name, context, all_orders, settings)
        if len(all_orders) > before:
            print(f"[+] Tái sử dụng session thành công cho {shop_name}.")
            return True
    except Exception as exc:
        print(f"[-] Không tái sử dụng được session {shop_name}: {exc}")
    finally:
        browser.close()
    return False


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


def solve_recaptcha_via_omocaptcha(page_url: str, site_key: str, api_key: str) -> str | None:
    if not api_key:
        return None
    print("[*] Đang gửi yêu cầu giải ReCAPTCHA lên OmoCaptcha...")
    try:
        create_task_url = "https://omocaptcha.com"
        payload = {
            "api_token": api_key,
            "task_type": "RecaptchaV2TaskProxyless",
            "data": {"page_url": page_url, "site_key": site_key},
        }
        res = requests.post(create_task_url, json=payload, timeout=10)
        task_data = res.json()

        if not task_data.get("error") and task_data.get("task_id"):
            task_id = task_data["task_id"]
            get_result_url = "https://omocaptcha.com"
            for _ in range(20):
                time.sleep(3)
                result_res = requests.post(
                    get_result_url,
                    json={"api_token": api_key, "task_id": task_id},
                    timeout=10,
                )
                result_data = result_res.json()
                if result_data.get("status") == "SUCCESS":
                    print("[+] OmoCaptcha đã giải Captcha thành công!")
                    return result_data.get("result")
                if result_data.get("status") == "FAILURE":
                    break
        print("[-] OmoCaptcha không thể giải mã tác vụ này.")
    except Exception as exc:
        print(f"[-] Lỗi kết nối tới OmoCaptcha: {exc}")
    return None


def fetch_and_parse_orders(
    shop_name: str,
    context: BrowserContext,
    all_orders_list: list[dict[str, Any]],
    settings: dict[str, Any],
) -> None:
    print(f"[*] Đang cào dữ liệu đơn hàng cho shop: {shop_name}...")
    days_back = int(settings.get("days_back", 3))
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    api_url = f"https://{shop_name}.tpos.vn/api/SaleOnlineOrder/Search"
    payload = {
        "FromDate": start_date.strftime("%Y-%m-%d 00:00:00"),
        "ToDate": end_date.strftime("%Y-%m-%d 23:59:59"),
        "PageIndex": 1,
        "PageSize": int(settings.get("page_size", 250)),
        "IncludeDetails": True,
    }

    try:
        response = context.request.post(api_url, json=payload, timeout=15000)
        if response.status != 200:
            print(f"[-] API {shop_name} trả mã {response.status}")
            return

        api_data = response.json()
        orders = api_data.get("Results") or api_data.get("Data") or []
        count_shop_orders = 0

        for order in orders:
            status = order.get("ShippingStatusName") or order.get("StatusName") or "Đang giao"
            if not any(x in str(status).lower() for x in ["dang giao", "delivering", "đang giao", "bình thường"]):
                continue

            address = order.get("ShippingAddress") or order.get("ReceiverAddress") or "N/A"
            products = order.get("OrderDetails") or []
            p_names = [p.get("ProductName", "Sản phẩm") for p in products]
            p_qtys = [str(p.get("Quantity", 1)) for p in products]

            all_orders_list.append({
                "vùng miền": detect_region_from_address(address),
                "tên shop": f"{shop_name}.tpos.vn",
                "mã vận đơn": order.get("TrackingCode") or "N/A",
                "đơn vị vận chuyển": order.get("CarrierName") or "J&T Express",
                "tên khách": order.get("CustomerName") or "N/A",
                "số điện thoại": order.get("CustomerPhone") or "N/A",
                "địa chỉ nhận hàng": address,
                "sản phẩm": ", ".join(p_names) if p_names else "N/A",
                "số lượng": ", ".join(p_qtys) if p_qtys else "0",
                "tổng tiền": order.get("TotalAmount") or 0,
                "trạng thái": status,
                "cod": order.get("CodAmount") or 0,
                "ngày cập nhật": order.get("DateUpdated") or "N/A",
            })
            count_shop_orders += 1

        print(f"[+] Đã gom {count_shop_orders} đơn 'Đang giao' từ shop {shop_name}.")
    except Exception as exc:
        print(f"[-] Không thể gọi dữ liệu từ API: {exc}")


def process_account(
    account: dict[str, Any],
    settings: dict[str, Any],
    session_dir: Path,
    all_orders: list[dict[str, Any]],
    playwright_instance: Any,
    proxy_cfg: dict[str, Any],
) -> None:
    parsed = parse_account(account)
    if not parsed:
        shop_hint = account.get("shop", "?")
        print(f"[-] Bỏ qua tài khoản {shop_hint}: thiếu shop/username/password.")
        return

    shop_name, username, password = parsed
    proxy_config = build_playwright_proxy(proxy_cfg)
    if is_vps_environment() and not proxy_config:
        print(f"[!] VPS shop {shop_name}: chưa có proxy — dễ bị TPOS/ReCAPTCHA chặn.")

    if try_reuse_session(
        shop_name, session_dir, settings, all_orders, playwright_instance, proxy_config
    ):
        return

    omocaptcha_key = str(settings.get("omocaptcha_api_key", "")).strip()
    headless = resolve_headless(settings)
    ab = anti_block_settings(settings)
    typing_delay = int(ab.get("human_typing_delay_ms", 80))

    print(f"\n================ Shop: {shop_name}.tpos.vn ================")

    browser = playwright_instance.chromium.launch(
        headless=headless,
        proxy=proxy_config,
        args=STEALTH_LAUNCH_ARGS,
    )
    context = browser.new_context(**browser_context_options(settings))
    page = context.new_page()
    apply_stealth_init_script(page)

    try:
        login_url = f"https://{shop_name}.tpos.vn/#/account/login"
        page.goto(login_url, timeout=20000)
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass

        user_selector = 'input[ng-model*="Email"], input[type="text"]'
        page.wait_for_selector(user_selector, timeout=5000)

        iframe_locator = page.locator("iframe[src*='recaptcha/api2/anchor']").first
        if iframe_locator.count() > 0 and omocaptcha_key:
            print("[!] Phát hiện Google ReCAPTCHA trên TPos!")
            src_attr = iframe_locator.get_attribute("src") or ""
            if "k=" in src_attr:
                site_key = src_attr.split("k=")[1].split("&")[0]
                g_res = solve_recaptcha_via_omocaptcha(page.url, site_key, omocaptcha_key)
                if g_res:
                    page.evaluate(
                        f'document.getElementById("g-recaptcha-response").innerHTML="{g_res}";'
                    )
                    print("[+] Đã nạp mã Bypass ReCAPTCHA thành công.")

        page.locator(user_selector).first.fill("", timeout=2000)
        page.locator(user_selector).first.type(username, delay=typing_delay)
        pass_selector = "input[type='password'], input#Password"
        page.locator(pass_selector).first.fill("", timeout=2000)
        page.locator(pass_selector).first.type(password, delay=typing_delay)
        time.sleep(random.uniform(0.4, 1.2))

        btn_selector = "button[type='submit'], button:has-text('Đăng nhập')"
        page.locator(btn_selector).first.click(timeout=4000)

        try:
            page.wait_for_url("**/desktop**", timeout=12000)
        except Exception:
            pass

        if "login" in page.url:
            print(f"[-] Thất bại: Sai mật khẩu shop {shop_name}.")
            return

        print(f"[+] Đăng nhập THÀNH CÔNG shop: {shop_name}")

        storage_state = context.storage_state()
        session_file = session_dir / f"{shop_name}_session.json"
        session_file.write_text(
            json.dumps(storage_state, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )

        fetch_and_parse_orders(shop_name, context, all_orders, settings)
    finally:
        browser.close()
        time.sleep(0.5)


def resolve_path(settings: dict[str, Any], key: str, default: str) -> Path:
    raw = str(settings.get(key, default))
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def run_automation() -> int:
    try:
        config = load_config()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[-] Lỗi config: {exc}", file=sys.stderr)
        return 2

    settings = config.get("settings", {})
    session_dir = resolve_path(settings, "session_dir", "outputs/tpos_sessions")
    session_dir.mkdir(parents=True, exist_ok=True)
    output_path = resolve_path(settings, "output_excel", "outputs/báo_cáo_đơn_hàng_tpos.xlsx")

    all_extracted_orders: list[dict[str, Any]] = []
    accounts = config["accounts"]
    proxy_pool = load_proxy_pool(config)

    with sync_playwright() as playwright_instance:
        for index, account in enumerate(accounts, start=1):
            if index > 1:
                sleep_between_accounts(settings)
            print(f"\n>>> Tài khoản {index}/{len(accounts)}")
            try:
                proxy_cfg = resolve_account_proxy(account, index - 1, proxy_pool, settings)
                process_account(
                    account,
                    settings,
                    session_dir,
                    all_extracted_orders,
                    playwright_instance,
                    proxy_cfg,
                )
            except Exception as exc:
                shop_hint = account.get("shop", account.get("username", "?"))
                print(f"[-] Lỗi xử lý tài khoản {shop_hint}: {exc}")

    if not all_extracted_orders:
        print("\n[-] Không lấy được đơn hàng. Kiểm tra config_tiktok.json.")
        return 1

    df = pd.DataFrame(all_extracted_orders)[COLUMNS_ORDER]
    df.to_excel(output_path, index=False)
    print(
        f"\n[+] Đã xuất {len(all_extracted_orders)} đơn hàng ra Excel: {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_automation())
