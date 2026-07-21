# Notes extracted from uploaded BM workers

- Default shop id: `1530618`
- Orders endpoint: `https://pos.pancake.vn/api/v1/shops/{shop_id}/orders`
- Token via `get_pancake_token()` / settings `pancake_token` / `pancake_pos_token`
- Optional headers setting: `pancake_headers`
- Page size clamped 10..20
- New standalone port: `scripts/pancake_order_sync_worker.py`
