#!/usr/bin/env python3
"""Fetch last N days of ASUNMEE orders and produce accessible speech output.

For users who cannot operate UI:
  - Excel report
  - Vietnamese MP3 summary (gTTS)
  - Auto-speaking HTML (Web Speech API, opens and reads aloud)

Usage:
  python3 speak_orders_accessibility.py --days 7 --telegram
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

try:
    from openpyxl import Workbook
except ImportError:
    Workbook = None

try:
    from gtts import gTTS
except ImportError:
    gTTS = None

from pancake_pos_client import auth_ready, fetch_shop_orders, missing_auth_names, resolve_credentials


ASUNMEE_ENV = Path("/home/ubuntu/.config/scantool/asunmee.env")
DEFAULT_OUT = Path("/tmp/pancake_reports")


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


def parse_args():
    load_extra_env()
    p = argparse.ArgumentParser(description="Accessible order fetch + read-aloud for disability support.")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--shop-id", default=os.getenv("PANCAKE_POS_SHOP_IDS", "714934229").split(",")[0].strip())
    p.add_argument("--base-url", default=os.getenv("PANCAKE_POS_BASE_URL", "https://pos.pages.fm/api/v1"))
    p.add_argument("--max-pages", type=int, default=500)
    p.add_argument("--output-dir", default=str(DEFAULT_OUT))
    p.add_argument("--telegram", action="store_true")
    p.add_argument("--detail-speak", type=int, default=15, help="How many newest orders to include in spoken details.")
    return p.parse_args()


def parse_dt(value, tz):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def customer_fields(order):
    customer = order.get("customer") if isinstance(order.get("customer"), dict) else {}
    ship = order.get("shipping_address") if isinstance(order.get("shipping_address"), dict) else {}
    name = order.get("bill_full_name") or ship.get("full_name") or customer.get("name") or ""
    phone = order.get("bill_phone_number") or ship.get("phone_number") or ""
    return str(name or ""), str(phone or "")


def fetch_orders(creds, shop_id, base_url, cutoff, tz, max_pages):
    collected = []
    for page in range(1, max_pages + 1):
        rows = fetch_shop_orders(
            creds,
            shop_id,
            base_url,
            params={"limit": 100, "page_number": page, "page": page},
        )
        if not rows:
            break
        stop = False
        for order in rows:
            inserted = parse_dt(order.get("inserted_at"), tz)
            if inserted is not None and inserted < cutoff:
                stop = True
                continue
            collected.append(order)
        if stop:
            break
    return collected


def write_excel(orders, shop_id, path: Path):
    if Workbook is None:
        raise RuntimeError("openpyxl required")
    wb = Workbook()
    ws = wb.active
    ws.title = "orders"
    ws.append(
        ["shop_id", "order_id", "inserted_at", "status_name", "total_price", "customer_name", "customer_phone"]
    )
    for order in orders:
        name, phone = customer_fields(order)
        ws.append(
            [
                shop_id,
                order.get("id"),
                order.get("inserted_at"),
                order.get("status_name"),
                order.get("total_price") or order.get("total") or 0,
                name,
                phone,
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def build_speech(orders, shop_name, days, detail_speak):
    statuses = Counter()
    revenue = 0.0
    masked = 0
    for order in orders:
        statuses[str(order.get("status_name") or "unknown")] += 1
        try:
            revenue += float(order.get("total_price") or order.get("total") or 0)
        except Exception:
            pass
        name, phone = customer_fields(order)
        if "*" in name or "*" in phone:
            masked += 1
    top = ", ".join(f"{k} {v} đơn" for k, v in statuses.most_common(5))
    rev = f"{int(revenue):,}".replace(",", ".")
    summary = (
        f"Báo cáo hỗ trợ đặc biệt cho người khuyết tật. Shop {shop_name}. "
        f"Đơn hàng {days} ngày gần nhất. Tổng cộng {len(orders)} đơn. "
        f"Tổng giá trị khoảng {rev} đồng. Trạng thái phổ biến: {top}. "
        f"{masked} đơn vẫn bị che tên hoặc số điện thoại do chính sách API. "
        "File Excel và file âm thanh đã gửi Telegram."
    )
    details = []
    for i, order in enumerate(orders[: max(0, detail_speak)], 1):
        name, phone = customer_fields(order)
        total = order.get("total_price") or order.get("total") or 0
        details.append(
            f"Đơn {i}: mã {order.get('id')}, trạng thái {order.get('status_name')}, "
            f"giá {total}, khách {name or 'đang che'}, điện thoại {phone or 'đang che'}."
        )
    full = summary + (" " + " ".join(details) if details else "")
    return summary, full, dict(statuses), revenue, masked


def write_auto_speak_html(path: Path, title: str, speech_text: str, meta: dict):
    # Escape for JS string
    js_text = json.dumps(speech_text, ensure_ascii=False)
    html = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background:#0b1220; color:#f8fafc; margin:0; padding:24px; line-height:1.6; }}
    .card {{ max-width:820px; margin:0 auto; background:#111827; border:2px solid #94a3b8; border-radius:12px; padding:20px; }}
    button {{ font-size:18px; min-height:48px; padding:10px 16px; margin-right:8px; margin-top:8px; cursor:pointer; }}
    #live {{ position:absolute; left:-9999px; }}
    h1 {{ font-size:1.6rem; }}
  </style>
</head>
<body>
  <div class="card" role="main">
    <h1>{title}</h1>
    <p>Trang này <strong>tự đọc to</strong> cho người khuyết tật. Nếu trình duyệt chặn tự phát, bấm nút bên dưới.</p>
    <p><strong>Số đơn:</strong> {meta.get('count')} · <strong>Tổng tiền:</strong> {meta.get('revenue_text')}</p>
    <div role="toolbar" aria-label="Điều khiển đọc to">
      <button id="btn-play" type="button">Đọc to ngay</button>
      <button id="btn-stop" type="button">Dừng</button>
    </div>
    <div id="status" aria-live="assertive" role="status">Đang chuẩn bị đọc to…</div>
    <pre id="script" style="white-space:pre-wrap;margin-top:16px">{speech_text}</pre>
  </div>
  <div id="live" aria-live="assertive"></div>
  <script>
    const TEXT = {js_text};
    const statusEl = document.getElementById('status');
    const liveEl = document.getElementById('live');
    function speak() {{
      if (!('speechSynthesis' in window)) {{
        statusEl.textContent = 'Trình duyệt không hỗ trợ đọc to.';
        return;
      }}
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(TEXT);
      u.lang = 'vi-VN';
      u.rate = 0.95;
      u.onstart = () => {{ statusEl.textContent = 'Đang đọc to báo cáo đơn hàng…'; liveEl.textContent = 'Đang đọc to'; }};
      u.onend = () => {{ statusEl.textContent = 'Đã đọc xong.'; liveEl.textContent = 'Đã đọc xong'; }};
      window.speechSynthesis.speak(u);
    }}
    document.getElementById('btn-play').addEventListener('click', speak);
    document.getElementById('btn-stop').addEventListener('click', () => window.speechSynthesis.cancel());
    window.addEventListener('load', () => setTimeout(speak, 600));
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def send_telegram(bot_token, chat_id, files_with_captions):
    for path, caption in files_with_captions:
        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        with open(path, "rb") as handle:
            response = requests.post(
                url,
                data={"chat_id": chat_id, "caption": caption},
                files={"document": (Path(path).name, handle)},
                timeout=180,
            )
        response.raise_for_status()
        if not response.json().get("ok"):
            # fallback audio as voice if document fails for mp3? keep document
            raise RuntimeError(response.text)


def main():
    args = parse_args()
    creds = resolve_credentials()
    if not auth_ready(creds):
        print("Missing key: " + ", ".join(missing_auth_names(creds)), file=sys.stderr)
        return 2

    tz = ZoneInfo(os.getenv("REPORT_TIMEZONE", "Asia/Ho_Chi_Minh"))
    now = datetime.now(tz)
    cutoff = now - timedelta(days=max(1, args.days))
    orders = fetch_orders(creds, args.shop_id, args.base_url, cutoff, tz, args.max_pages)
    orders.sort(key=lambda o: str(o.get("inserted_at") or ""), reverse=True)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    excel = out_dir / f"asunmee-orders-last{args.days}d-a11y-{stamp}.xlsx"
    write_excel(orders, args.shop_id, excel)

    shop_name = os.getenv("PANCAKE_SHOP_NAME", "ASUNMEE")
    summary, full_speech, statuses, revenue, masked = build_speech(
        orders, shop_name, args.days, args.detail_speak
    )
    speech_txt = out_dir / f"asunmee-last{args.days}d-speech-{stamp}.txt"
    speech_json = out_dir / f"asunmee-last{args.days}d-speech-{stamp}.json"
    speech_mp3 = out_dir / f"asunmee-last{args.days}d-speech-{stamp}.mp3"
    speech_html = out_dir / f"asunmee-last{args.days}d-speak-{stamp}.html"

    speech_txt.write_text(full_speech, encoding="utf-8")
    meta = {
        "shop_id": args.shop_id,
        "shop_name": shop_name,
        "days": args.days,
        "count": len(orders),
        "revenue": revenue,
        "revenue_text": f"{int(revenue):,}".replace(",", ".") + " VND",
        "masked": masked,
        "statuses": statuses,
        "excel": str(excel),
        "speech_text": str(speech_txt),
        "generated_at": now.isoformat(),
        "mode": "disability_auto_speak",
    }
    speech_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_auto_speak_html(
        speech_html,
        f"Đọc to đơn {shop_name} {args.days} ngày",
        full_speech,
        meta,
    )

    if gTTS is None:
        print("gTTS missing; skip mp3", file=sys.stderr)
    else:
        gTTS(text=summary, lang="vi").save(str(speech_mp3))

    result = {
        **meta,
        "mp3": str(speech_mp3) if speech_mp3.exists() else "",
        "html_auto_speak": str(speech_html),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.telegram:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat:
            print("Telegram env missing", file=sys.stderr)
            return 1
        caption = (
            f"ASUNMEE {args.days} ngày — hỗ trợ khuyết tật\n"
            f"Đơn: {len(orders)} | Mask PII: {masked}\n"
            f"Doanh thu ~ {meta['revenue_text']}\n"
            f"Kèm Excel + MP3 đọc to + HTML tự đọc"
        )
        files = [(excel, caption)]
        if speech_mp3.exists():
            files.append((speech_mp3, "Bản đọc to (MP3) — mở để nghe"))
        files.append((speech_html, "HTML tự đọc to khi mở (Web Speech)"))
        send_telegram(token, chat, files)
        print(json.dumps({"telegram_sent": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
