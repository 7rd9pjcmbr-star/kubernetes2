/**
 * Pancake POS — Orders tab unmask hook (run in logged-in browser tab).
 *
 * Usage (DevTools Console on https://pos.pancake.vn/shop/<id>/order):
 *   1) Paste this entire file and press Enter
 *   2) Reload the page (hook re-installs via sessionStorage bootstrap) OR
 *      call: window.__pancakeUnmask.install({ persistReload: true }) then reload
 *   3) After table loads: window.__pancakeUnmask.patchNow()
 *   4) Export: window.__pancakeUnmask.downloadJson()
 *
 * What it does:
 *   - Hooks fetch + XHR to capture full order payloads (name/phone before UI mask)
 *   - Patches masked cells in the orders grid
 *   - Keeps a live index by order id / display code
 */
(function pancakeOrdersUnmaskHook(global) {
  "use strict";

  const NS = "__pancakeUnmask";
  const STORAGE_BOOT = "__pancake_unmask_boot_v1";
  const STORAGE_ORDERS = "__pancake_unmask_orders_v1";

  const MASK_RE = /(?:\*{2,}|\u2022{2,}|x{3,}|\.{3,}|•{2,})/i;
  const PHONE_HINT_RE = /(?:\+?84|0)\d[\d\s().-]{7,}/;
  const ORDER_URL_RE =
    /orders|get_orders|order_list|order\/list|shop\/\d+\/order|\/api\/v1\/shops\/\d+/i;

  const state = {
    installed: false,
    patchedCells: 0,
    lastPatchAt: null,
    ordersByKey: new Map(),
    observer: null,
    panel: null,
  };

  function nowIso() {
    return new Date().toISOString();
  }

  function loadPersistedOrders() {
    try {
      const raw = sessionStorage.getItem(STORAGE_ORDERS);
      if (!raw) return;
      const rows = JSON.parse(raw);
      if (!Array.isArray(rows)) return;
      rows.forEach(ingestOrder);
    } catch (_) {
      /* ignore */
    }
  }

  function persistOrders() {
    try {
      const rows = Array.from(state.ordersByKey.values());
      sessionStorage.setItem(STORAGE_ORDERS, JSON.stringify(rows.slice(0, 2000)));
    } catch (_) {
      /* ignore */
    }
  }

  function pickPhone(customer) {
    if (!customer || typeof customer !== "object") return "";
    if (customer.phone_numbers && Array.isArray(customer.phone_numbers)) {
      const joined = customer.phone_numbers.filter(Boolean).join(", ");
      if (joined) return String(joined);
    }
    return String(
      customer.phone_number ||
        customer.phone ||
        customer.shipping_phone ||
        customer.phoneNumber ||
        ""
    );
  }

  function pickName(customer, order) {
    if (customer && typeof customer === "object") {
      const name =
        customer.name ||
        customer.full_name ||
        customer.customer_name ||
        customer.display_name;
      if (name) return String(name);
    }
    return String(
      order.shipping_address?.full_name ||
        order.shipping_address?.name ||
        order.buyer_name ||
        order.customer_name ||
        ""
    );
  }

  function orderKeys(order) {
    const keys = [
      order.id,
      order.order_id,
      order.display_id,
      order.order_number,
      order.code,
      order.custom_id,
    ]
      .filter((v) => v !== undefined && v !== null && String(v).trim() !== "")
      .map((v) => String(v).trim());
    return Array.from(new Set(keys));
  }

  function ingestOrder(order) {
    if (!order || typeof order !== "object") return false;
    const customer = order.customer || order.buyer || {};
    const record = {
      id: order.id ?? order.order_id ?? null,
      display_id: order.display_id ?? order.order_number ?? order.code ?? null,
      inserted_at: order.inserted_at || order.created_at || null,
      status_name: order.status_name || order.status || null,
      total_price: order.total_price ?? order.total ?? null,
      customer_name: pickName(customer, order),
      customer_phone: pickPhone(customer) || String(order.shipping_address?.phone_number || ""),
      customer_id: customer.customer_id || customer.id || null,
      shop_id: order.shop_id || null,
      raw_customer: customer,
      captured_at: nowIso(),
    };
    if (!record.customer_name && !record.customer_phone) return false;

    let stored = false;
    for (const key of orderKeys(order)) {
      state.ordersByKey.set(key, record);
      stored = true;
    }
    if (!stored && record.id != null) {
      state.ordersByKey.set(String(record.id), record);
      stored = true;
    }
    return stored;
  }

  function walkOrders(node, depth) {
    if (!node || depth > 8) return 0;
    let count = 0;
    if (Array.isArray(node)) {
      for (const item of node) count += walkOrders(item, depth + 1);
      return count;
    }
    if (typeof node !== "object") return 0;

    const looksLikeOrder =
      ("customer" in node || "buyer" in node || "shipping_address" in node) &&
      ("id" in node || "order_id" in node || "display_id" in node);
    if (looksLikeOrder && ingestOrder(node)) count += 1;

    for (const key of ["data", "orders", "items", "results", "rows"]) {
      if (node[key]) count += walkOrders(node[key], depth + 1);
    }
    return count;
  }

  function maybeCapturePayload(url, payload) {
    if (!payload) return;
    const urlText = String(url || "");
    const force = ORDER_URL_RE.test(urlText);
    let added = 0;
    try {
      const data = typeof payload === "string" ? JSON.parse(payload) : payload;
      added = walkOrders(data, 0);
      if (!added && force && data && typeof data === "object") {
        added = walkOrders(data.data || data.orders || data, 0);
      }
    } catch (_) {
      return;
    }
    if (added > 0) {
      persistOrders();
      updatePanel(`captured +${added} (total ${state.ordersByKey.size})`);
      // Patch shortly after network paint.
      setTimeout(patchNow, 300);
      setTimeout(patchNow, 1200);
    }
  }

  function installNetworkHooks() {
    if (global.__pancakeUnmaskFetchHooked) return;
    global.__pancakeUnmaskFetchHooked = true;

    const originalFetch = global.fetch;
    if (typeof originalFetch === "function") {
      global.fetch = async function patchedFetch(input, init) {
        const response = await originalFetch.apply(this, arguments);
        try {
          const url = typeof input === "string" ? input : input && input.url;
          if (ORDER_URL_RE.test(String(url || ""))) {
            const clone = response.clone();
            clone
              .text()
              .then((text) => maybeCapturePayload(url, text))
              .catch(() => {});
          }
        } catch (_) {
          /* ignore */
        }
        return response;
      };
    }

    const XHR = global.XMLHttpRequest;
    if (XHR && XHR.prototype) {
      const open = XHR.prototype.open;
      const send = XHR.prototype.send;
      XHR.prototype.open = function (method, url) {
        this.__pancakeUrl = url;
        return open.apply(this, arguments);
      };
      XHR.prototype.send = function () {
        this.addEventListener("load", function () {
          try {
            maybeCapturePayload(this.__pancakeUrl, this.responseText);
          } catch (_) {
            /* ignore */
          }
        });
        return send.apply(this, arguments);
      };
    }
  }

  function textOf(el) {
    return (el && (el.innerText || el.textContent) || "").trim();
  }

  function isMaskedText(text) {
    if (!text) return false;
    if (MASK_RE.test(text)) return true;
    // Pancake often shows partial mask like 09****1234 or N*****n
    if (/(?:\d\*{2,}|\*{2,}\d|[A-Za-zÀ-ỹ]\*{2,}|\*{2,}[A-Za-zÀ-ỹ])/.test(text)) return true;
    return false;
  }

  function nearestRow(el) {
    return (
      el.closest("tr") ||
      el.closest('[role="row"]') ||
      el.closest(".ant-table-row") ||
      el.closest("[data-row-key]") ||
      el.parentElement
    );
  }

  function findRecordForRow(row) {
    if (!row) return null;
    const rowText = textOf(row);
    for (const [key, record] of state.ordersByKey.entries()) {
      if (key && rowText.includes(key)) return record;
    }
    // Try data attributes.
    const attrKeys = [
      row.getAttribute("data-row-key"),
      row.getAttribute("data-order-id"),
      row.getAttribute("data-id"),
    ].filter(Boolean);
    for (const key of attrKeys) {
      if (state.ordersByKey.has(String(key))) return state.ordersByKey.get(String(key));
    }
    return null;
  }

  function setCellText(el, value) {
    if (!el || value == null || value === "") return false;
    const next = String(value);
    if (textOf(el) === next) return false;
    el.textContent = next;
    el.setAttribute("title", next);
    el.style.outline = "1px solid rgba(16,185,129,.55)";
    el.dataset.pancakeUnmasked = "1";
    return true;
  }

  function patchCell(el, record) {
    if (!el || !record) return 0;
    if (el.dataset && el.dataset.pancakeUnmasked === "1" && !isMaskedText(textOf(el))) return 0;
    const text = textOf(el);
    if (!text && !el.closest("td,th,[role='cell']")) return 0;

    const lower = (el.className || "") + " " + (el.getAttribute("data-column") || "");
    let changed = 0;

    const phoneish =
      /phone|sđt|sdt|tel|mobile|điện thoại|dien thoai/i.test(lower) ||
      PHONE_HINT_RE.test(text) ||
      isMaskedText(text);
    const nameish =
      /name|tên|ten|customer|khách|khach/i.test(lower) ||
      (isMaskedText(text) && !PHONE_HINT_RE.test(text));

    if (phoneish && record.customer_phone && (isMaskedText(text) || !text || text.includes("*"))) {
      if (setCellText(el, record.customer_phone)) changed += 1;
    } else if (nameish && record.customer_name && (isMaskedText(text) || text.includes("*"))) {
      if (setCellText(el, record.customer_name)) changed += 1;
    } else if (isMaskedText(text)) {
      // Heuristic fallback: phone-like mask vs name mask.
      if (/\d/.test(text) && record.customer_phone) {
        if (setCellText(el, record.customer_phone)) changed += 1;
      } else if (record.customer_name) {
        if (setCellText(el, record.customer_name)) changed += 1;
      }
    }
    return changed;
  }

  function collectCandidateCells(root) {
    const scope = root || document;
    const nodes = scope.querySelectorAll(
      "td, th, [role='cell'], .ant-table-cell, [class*='cell'], span, div, a"
    );
    const out = [];
    nodes.forEach((el) => {
      if (!(el instanceof HTMLElement)) return;
      if (el.closest("#" + NS + "Panel")) return;
      const text = textOf(el);
      if (!text) return;
      if (text.length > 80) return;
      if (el.children && el.children.length > 3) return;
      if (isMaskedText(text) || PHONE_HINT_RE.test(text) || text.includes("*")) out.push(el);
    });
    return out;
  }

  function patchNow() {
    let changed = 0;
    const cells = collectCandidateCells(document);
    for (const el of cells) {
      const row = nearestRow(el);
      const record = findRecordForRow(row);
      if (!record) continue;
      changed += patchCell(el, record);
    }

    // Second pass: match order keys against table rows only.
    const rows = document.querySelectorAll("tr, [role='row'], .ant-table-row, [data-row-key]");
    for (const row of rows) {
      const record = findRecordForRow(row);
      if (!record) continue;
      collectCandidateCells(row).forEach((el) => {
        changed += patchCell(el, record);
      });
    }

    state.patchedCells += changed;
    state.lastPatchAt = nowIso();
    updatePanel(`patched +${changed} (session ${state.patchedCells})`);
    return {
      changed,
      totalOrders: state.ordersByKey.size,
      patchedCells: state.patchedCells,
      maskedLeft: countMaskedLeft(),
    };
  }

  function countMaskedLeft() {
    return collectCandidateCells(document).filter((el) => isMaskedText(textOf(el))).length;
  }

  function ensurePanel() {
    if (state.panel && document.body.contains(state.panel)) return state.panel;
    const panel = document.createElement("div");
    panel.id = NS + "Panel";
    panel.style.cssText = [
      "position:fixed",
      "right:12px",
      "bottom:12px",
      "z-index:2147483646",
      "background:#0f172a",
      "color:#e2e8f0",
      "font:12px/1.4 ui-sans-serif,system-ui,sans-serif",
      "padding:10px 12px",
      "border-radius:10px",
      "box-shadow:0 8px 24px rgba(0,0,0,.35)",
      "max-width:280px",
    ].join(";");
    panel.innerHTML =
      '<div style="font-weight:700;margin-bottom:4px">Pancake Unmask</div>' +
      '<div data-role="status">idle</div>' +
      '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">' +
      '<button type="button" data-act="patch">Patch</button>' +
      '<button type="button" data-act="export">Export JSON</button>' +
      '<button type="button" data-act="count">Count mask</button>' +
      "</div>";
    panel.querySelectorAll("button").forEach((btn) => {
      btn.style.cssText =
        "cursor:pointer;border:0;border-radius:6px;padding:4px 8px;background:#334155;color:#fff";
    });
    panel.addEventListener("click", (ev) => {
      const act = ev.target && ev.target.getAttribute("data-act");
      if (act === "patch") console.log("[pancake-unmask]", patchNow());
      if (act === "export") downloadJson();
      if (act === "count") updatePanel("masked left: " + countMaskedLeft());
    });
    document.documentElement.appendChild(panel);
    state.panel = panel;
    return panel;
  }

  function updatePanel(message) {
    const panel = ensurePanel();
    const status = panel.querySelector('[data-role="status"]');
    if (status) {
      status.textContent =
        message +
        ` | orders=${state.ordersByKey.size} | masked=${countMaskedLeft()}`;
    }
  }

  function installObserver() {
    if (state.observer) return;
    state.observer = new MutationObserver(() => {
      if (state._patchTimer) clearTimeout(state._patchTimer);
      state._patchTimer = setTimeout(patchNow, 400);
    });
    state.observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  function exportRows() {
    return Array.from(state.ordersByKey.values()).map((row) => ({
      shop_id: row.shop_id,
      order_id: row.id,
      display_id: row.display_id,
      inserted_at: row.inserted_at,
      status_name: row.status_name,
      total_price: row.total_price,
      customer_name: row.customer_name,
      customer_phone: row.customer_phone,
      customer_id: row.customer_id,
      captured_at: row.captured_at,
    }));
  }

  function downloadJson() {
    const rows = exportRows();
    const blob = new Blob([JSON.stringify({ exported_at: nowIso(), orders: rows }, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `pancake-orders-unmasked-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    updatePanel(`exported ${rows.length} rows`);
    return rows.length;
  }

  function install(options) {
    const opts = options || {};
    loadPersistedOrders();
    installNetworkHooks();
    ensurePanel();
    installObserver();
    state.installed = true;

    if (opts.persistReload) {
      sessionStorage.setItem(STORAGE_BOOT, "1");
    }

    updatePanel("hook installed");
    setTimeout(patchNow, 500);
    return api.status();
  }

  function autoBootIfNeeded() {
    try {
      if (sessionStorage.getItem(STORAGE_BOOT) === "1") {
        install({ persistReload: true });
      }
    } catch (_) {
      /* ignore */
    }
  }

  const api = {
    install,
    patchNow,
    downloadJson,
    exportRows,
    countMaskedLeft,
    status() {
      return {
        installed: state.installed,
        orders: state.ordersByKey.size,
        patchedCells: state.patchedCells,
        maskedLeft: countMaskedLeft(),
        lastPatchAt: state.lastPatchAt,
      };
    },
  };

  global[NS] = api;
  autoBootIfNeeded();

  // If pasted manually, install immediately.
  if (!state.installed) install({ persistReload: true });

  console.log(
    "[pancake-unmask] ready. Reload page to capture get_orders, then patch. API:",
    NS
  );
})(window);
