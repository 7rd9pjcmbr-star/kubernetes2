/**
 * Pancake POS — Accessibility-assisted order unmask
 *
 * Designed for assistive tech parity: screen readers often receive the
 * real accessible name (aria-label / labelledby / title) even when the
 * visible cell is masked.
 *
 * Usage (logged-in tab):
 *   https://pos.pancake.vn/shop/714934229/order
 *   1) F12 → Console → paste this file → Enter
 *   2) window.__pancakeA11y.scan()
 *   3) window.__pancakeA11y.downloadJson()
 *
 * Optional Chrome DevTools:
 *   Elements → Accessibility pane → inspect row cells for Name/Value
 */
(function pancakeA11yUnmask(global) {
  "use strict";

  const NS = "__pancakeA11y";
  const MASK_RE = /(?:\*{2,}|\u2022{2,}|x{3,}|\.{3,}|•{2,}|\d\*{2,}|\*{2,}\d)/i;
  const PHONE_RE = /(?:\+?84|0)\d[\d\s().-]{7,}\d/;
  const ORDER_ID_RE = /\b(?:DH[-_]?\d{4}[-_]?\d+|\d{15,}|[A-Z0-9]{10,})\b/i;

  const state = {
    rows: [],
    lastScanAt: null,
    panel: null,
  };

  function nowIso() {
    return new Date().toISOString();
  }

  function isMasked(text) {
    return !text ? false : MASK_RE.test(String(text));
  }

  function clean(text) {
    return String(text || "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function resolveLabelledBy(el) {
    const ids = (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean);
    if (!ids.length) return "";
    return ids
      .map((id) => {
        const node = document.getElementById(id);
        return node ? clean(node.innerText || node.textContent) : "";
      })
      .filter(Boolean)
      .join(" ");
  }

  function resolveDescribedBy(el) {
    const ids = (el.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
    if (!ids.length) return "";
    return ids
      .map((id) => {
        const node = document.getElementById(id);
        return node ? clean(node.innerText || node.textContent) : "";
      })
      .filter(Boolean)
      .join(" ");
  }

  function visibleText(el) {
    return clean(el.innerText || el.textContent || "");
  }

  function a11yCandidates(el) {
    const out = [];
    const push = (source, value) => {
      const v = clean(value);
      if (v) out.push({ source, value: v, masked: isMasked(v) });
    };
    push("aria-label", el.getAttribute("aria-label"));
    push("aria-labelledby", resolveLabelledBy(el));
    push("aria-description", el.getAttribute("aria-description"));
    push("aria-describedby", resolveDescribedBy(el));
    push("title", el.getAttribute("title"));
    push("alt", el.getAttribute("alt"));
    push("data-tip", el.getAttribute("data-tip") || el.getAttribute("data-tooltip"));
    push("placeholder", el.getAttribute("placeholder"));
    push("value", el.value);
    // visually-hidden / sr-only siblings often carry full text for AT
    el.querySelectorAll(
      ".sr-only, .visually-hidden, .ant-sr-only, [class*='sr-only'], [class*='visually-hidden'], [style*='clip'], [aria-hidden='false']"
    ).forEach((node, idx) => push("sr-only-" + idx, visibleText(node)));
    push("visible", visibleText(el));
    return out;
  }

  async function computedAccessibleName(el) {
    try {
      if (typeof global.getComputedAccessibleNode === "function") {
        const ax = await global.getComputedAccessibleNode(el);
        if (ax && ax.name) return clean(ax.name);
      }
    } catch (_) {
      /* experimental API may throw */
    }
    return "";
  }

  function classifyValue(value) {
    if (PHONE_RE.test(value.replace(/\s+/g, ""))) return "phone";
    if (ORDER_ID_RE.test(value) && value.length <= 40) return "order_id";
    if (/@/.test(value)) return "email";
    if (value.length >= 2 && value.length <= 80 && !isMasked(value)) return "name_or_text";
    if (isMasked(value) && PHONE_RE.test(value.replace(/\*/g, "0"))) return "phone_masked";
    if (isMasked(value)) return "masked_text";
    return "text";
  }

  function preferUnmasked(candidates) {
    const clear = candidates.filter((c) => !c.masked && c.value);
    if (clear.length) return clear[0];
    return candidates[0] || null;
  }

  function rowNodes() {
    return Array.from(
      document.querySelectorAll("tr, [role='row'], .ant-table-row, [data-row-key]")
    ).filter((el) => el && el.children && el.children.length);
  }

  function cellNodes(row) {
    return Array.from(
      row.querySelectorAll("td, th, [role='cell'], [role='gridcell'], .ant-table-cell")
    );
  }

  async function scanRow(row) {
    const record = {
      order_id: "",
      customer_name: "",
      customer_phone: "",
      extras: [],
      a11y_hits: [],
      source: "accessibility",
      captured_at: nowIso(),
    };

    const cells = cellNodes(row);
    const targets = cells.length ? cells : [row];

    for (const cell of targets) {
      const cands = a11yCandidates(cell);
      const computed = await computedAccessibleName(cell);
      if (computed) cands.unshift({ source: "computedAccessibleNode", value: computed, masked: isMasked(computed) });

      for (const cand of cands) {
        const kind = classifyValue(cand.value);
        record.a11y_hits.push({ kind, ...cand });
        if (kind === "order_id" && !record.order_id) record.order_id = cand.value;
        if (kind === "phone" && !record.customer_phone) record.customer_phone = cand.value;
        if (kind === "name_or_text" && !record.customer_name && cand.source !== "visible") {
          // Prefer non-visible a11y sources for names (visible may be masked later)
          record.customer_name = cand.value;
        }
      }

      // If visible is masked but aria-label clear exists, force pick.
      const best = preferUnmasked(cands.filter((c) => c.source !== "visible"));
      if (best) {
        const kind = classifyValue(best.value);
        if (kind === "phone") record.customer_phone = best.value;
        if (kind === "name_or_text" && !PHONE_RE.test(best.value)) record.customer_name = best.value;
        if (kind === "order_id") record.order_id = record.order_id || best.value;
      }
    }

    // Fallback order id from row attributes / visible text.
    if (!record.order_id) {
      const attr =
        row.getAttribute("data-row-key") ||
        row.getAttribute("data-order-id") ||
        row.getAttribute("data-id") ||
        "";
      if (attr) record.order_id = attr;
      else {
        const m = visibleText(row).match(ORDER_ID_RE);
        if (m) record.order_id = m[0];
      }
    }

    const useful =
      (record.customer_name && !isMasked(record.customer_name)) ||
      (record.customer_phone && !isMasked(record.customer_phone));
    return useful ? record : null;
  }

  async function scan() {
    const rows = [];
    for (const row of rowNodes()) {
      const rec = await scanRow(row);
      if (rec) rows.push(rec);
    }
    // Deduplicate by order_id when possible.
    const byId = new Map();
    rows.forEach((r, idx) => {
      const key = r.order_id || ("row-" + idx);
      const prev = byId.get(key);
      if (!prev) byId.set(key, r);
      else {
        byId.set(key, {
          ...prev,
          customer_name: (!isMasked(r.customer_name) && r.customer_name) || prev.customer_name,
          customer_phone: (!isMasked(r.customer_phone) && r.customer_phone) || prev.customer_phone,
          a11y_hits: (prev.a11y_hits || []).concat(r.a11y_hits || []),
        });
      }
    });
    state.rows = Array.from(byId.values());
    state.lastScanAt = nowIso();
    updatePanel(
      "a11y rows=" +
        state.rows.length +
        " clear_phone=" +
        state.rows.filter((r) => r.customer_phone && !isMasked(r.customer_phone)).length +
        " clear_name=" +
        state.rows.filter((r) => r.customer_name && !isMasked(r.customer_name)).length
    );
    // Also feed network unmask hook if present.
    if (global.__pancakeUnmask && typeof global.__pancakeUnmask.ingestA11y === "function") {
      global.__pancakeUnmask.ingestA11y(state.rows);
    }
    console.log("[pancake-a11y]", api.status());
    return api.status();
  }

  function patchFromA11y() {
    let changed = 0;
    const index = new Map();
    state.rows.forEach((r) => {
      if (r.order_id) index.set(String(r.order_id), r);
    });
    rowNodes().forEach((row) => {
      const key =
        row.getAttribute("data-row-key") ||
        row.getAttribute("data-order-id") ||
        (visibleText(row).match(ORDER_ID_RE) || [])[0];
      const rec = key ? index.get(String(key)) : null;
      if (!rec) return;
      cellNodes(row).forEach((cell) => {
        const visible = visibleText(cell);
        if (!isMasked(visible)) return;
        if (rec.customer_phone && (PHONE_RE.test(visible.replace(/\*/g, "0")) || visible.includes("*"))) {
          // Heuristic: if masked phone-like, write phone
          if (/\d/.test(visible) && rec.customer_phone) {
            cell.textContent = rec.customer_phone;
            cell.setAttribute("aria-label", rec.customer_phone);
            cell.style.outline = "1px solid rgba(59,130,246,.7)";
            changed += 1;
            return;
          }
        }
        if (rec.customer_name && isMasked(visible) && !/\d{4,}/.test(visible)) {
          cell.textContent = rec.customer_name;
          cell.setAttribute("aria-label", rec.customer_name);
          cell.style.outline = "1px solid rgba(59,130,246,.7)";
          changed += 1;
        }
      });
    });
    updatePanel("patched " + changed);
    return { changed, rows: state.rows.length };
  }

  function downloadJson() {
    const payload = {
      exported_at: nowIso(),
      method: "accessibility",
      shop_hint: "714934229/ASUNMEE",
      orders: state.rows.map((r) => ({
        order_id: r.order_id,
        customer_name: r.customer_name,
        customer_phone: r.customer_phone,
        captured_at: r.captured_at,
        a11y_sources: (r.a11y_hits || [])
          .filter((h) => !h.masked)
          .map((h) => ({ source: h.source, kind: h.kind, value: h.value })),
      })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "pancake-a11y-unmasked-" + Date.now() + ".json";
    a.click();
    URL.revokeObjectURL(a.href);
    updatePanel("exported " + payload.orders.length);
    return payload.orders.length;
  }

  function ensurePanel() {
    if (state.panel && document.body.contains(state.panel)) return state.panel;
    const panel = document.createElement("div");
    panel.id = NS + "Panel";
    panel.setAttribute("role", "region");
    panel.setAttribute("aria-label", "Pancake accessibility unmask tools");
    panel.style.cssText =
      "position:fixed;left:12px;bottom:12px;z-index:2147483646;background:#1e3a5f;color:#e2e8f0;" +
      "font:12px/1.4 ui-sans-serif,system-ui,sans-serif;padding:10px 12px;border-radius:10px;" +
      "box-shadow:0 8px 24px rgba(0,0,0,.35);max-width:300px";
    panel.innerHTML =
      '<div style="font-weight:700;margin-bottom:4px">A11y Unmask (AT)</div>' +
      '<div data-role="status">idle</div>' +
      '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap">' +
      '<button type="button" data-act="scan">Scan a11y</button>' +
      '<button type="button" data-act="patch">Patch UI</button>' +
      '<button type="button" data-act="export">Export JSON</button>' +
      "</div>";
    panel.querySelectorAll("button").forEach((btn) => {
      btn.style.cssText =
        "cursor:pointer;border:0;border-radius:6px;padding:4px 8px;background:#334155;color:#fff";
      btn.setAttribute("type", "button");
    });
    panel.addEventListener("click", (ev) => {
      const act = ev.target && ev.target.getAttribute("data-act");
      if (act === "scan") scan();
      if (act === "patch") console.log("[pancake-a11y]", patchFromA11y());
      if (act === "export") downloadJson();
    });
    document.documentElement.appendChild(panel);
    state.panel = panel;
    return panel;
  }

  function updatePanel(message) {
    const panel = ensurePanel();
    const status = panel.querySelector('[data-role="status"]');
    if (status) status.textContent = message;
  }

  const api = {
    scan,
    patchFromA11y,
    downloadJson,
    status() {
      return {
        rows: state.rows.length,
        clear_name: state.rows.filter((r) => r.customer_name && !isMasked(r.customer_name)).length,
        clear_phone: state.rows.filter((r) => r.customer_phone && !isMasked(r.customer_phone)).length,
        lastScanAt: state.lastScanAt,
      };
    },
  };

  global[NS] = api;
  ensurePanel();
  updatePanel("ready — click Scan a11y");
  console.log("[pancake-a11y] ready. API:", NS, "→ scan / patchFromA11y / downloadJson");
})(window);
