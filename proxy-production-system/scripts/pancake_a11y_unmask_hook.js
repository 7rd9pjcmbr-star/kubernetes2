/**
 * Pancake POS — Hỗ trợ đặc biệt cho người khuyết tật (Accessibility Suite)
 *
 * Mục tiêu: người dùng AT (NVDA/JAWS/VoiceOver/TalkBack) đọc được tên/SĐT
 * đơn hàng ngay cả khi UI đang mask, điều khiển bằng bàn phím, tương phản cao.
 *
 * Dùng trên tab đã đăng nhập:
 *   https://pos.pancake.vn/shop/714934229/order
 *
 * Phím tắt:
 *   Alt+Shift+S  — Quét Accessibility
 *   Alt+Shift+P  — Vá UI từ kết quả a11y
 *   Alt+Shift+E  — Export JSON
 *   Alt+Shift+H  — Bật/tắt tương phản cao + chữ lớn
 *   Alt+Shift+R  — Đọc to tóm tắt (aria-live)
 *   Alt+Shift+/  — Hiện trợ giúp
 *
 * API: window.__pancakeA11y
 */
(function pancakeA11yDisabilitySupport(global) {
  "use strict";

  const NS = "__pancakeA11y";
  const MASK_RE = /(?:\*{2,}|\u2022{2,}|x{3,}|\.{3,}|•{2,}|\d\*{2,}|\*{2,}\d)/i;
  const PHONE_RE = /(?:\+?84|0)\d[\d\s().-]{7,}\d/;
  const ORDER_ID_RE = /\b(?:DH[-_]?\d{4}[-_]?\d+|\d{15,}|[A-Z0-9]{10,})\b/i;

  const state = {
    rows: [],
    lastScanAt: null,
    panel: null,
    live: null,
    highContrast: false,
    largeText: false,
    helpOpen: false,
  };

  function nowIso() {
    return new Date().toISOString();
  }

  function isMasked(text) {
    return !text ? false : MASK_RE.test(String(text));
  }

  function clean(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function announce(message, assertive) {
    ensureLiveRegion();
    const node = state.live;
    node.setAttribute("aria-live", assertive ? "assertive" : "polite");
    // Clear then set so AT re-announces identical strings.
    node.textContent = "";
    setTimeout(() => {
      node.textContent = String(message || "");
    }, 30);
    updatePanel(message);
  }

  function ensureLiveRegion() {
    if (state.live && document.body.contains(state.live)) return state.live;
    const live = document.createElement("div");
    live.id = NS + "Live";
    live.setAttribute("role", "status");
    live.setAttribute("aria-live", "polite");
    live.setAttribute("aria-atomic", "true");
    live.className = "sr-only";
    live.style.cssText =
      "position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;" +
      "clip:rect(0,0,0,0);white-space:nowrap;border:0";
    document.documentElement.appendChild(live);
    state.live = live;
    return live;
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
    if ("value" in el) push("value", el.value);
    el.querySelectorAll(
      ".sr-only, .visually-hidden, .ant-sr-only, [class*='sr-only'], [class*='visually-hidden']"
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
    } catch (_) {}
    return "";
  }

  function classifyValue(value) {
    if (PHONE_RE.test(value.replace(/\s+/g, ""))) return "phone";
    if (ORDER_ID_RE.test(value) && value.length <= 40) return "order_id";
    if (/@/.test(value)) return "email";
    if (value.length >= 2 && value.length <= 80 && !isMasked(value)) return "name_or_text";
    if (isMasked(value)) return "masked_text";
    return "text";
  }

  function preferUnmasked(candidates) {
    const clear = candidates.filter((c) => !c.masked && c.value);
    return clear[0] || candidates[0] || null;
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
      a11y_hits: [],
      source: "accessibility",
      captured_at: nowIso(),
    };
    const targets = cellNodes(row);
    const cells = targets.length ? targets : [row];

    for (const cell of cells) {
      const cands = a11yCandidates(cell);
      const computed = await computedAccessibleName(cell);
      if (computed) {
        cands.unshift({
          source: "computedAccessibleNode",
          value: computed,
          masked: isMasked(computed),
        });
      }
      for (const cand of cands) {
        const kind = classifyValue(cand.value);
        record.a11y_hits.push({ kind, ...cand });
        if (kind === "order_id" && !record.order_id) record.order_id = cand.value;
        if (kind === "phone" && !record.customer_phone) record.customer_phone = cand.value;
        if (kind === "name_or_text" && !record.customer_name && cand.source !== "visible") {
          record.customer_name = cand.value;
        }
      }
      const best = preferUnmasked(cands.filter((c) => c.source !== "visible"));
      if (best) {
        const kind = classifyValue(best.value);
        if (kind === "phone") record.customer_phone = best.value;
        if (kind === "name_or_text" && !PHONE_RE.test(best.value)) record.customer_name = best.value;
        if (kind === "order_id") record.order_id = record.order_id || best.value;
      }
    }

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
    announce("Đang quét accessibility tree để lấy đơn giải che…", false);
    const collected = [];
    const rows = rowNodes();
    for (let i = 0; i < rows.length; i += 1) {
      const rec = await scanRow(rows[i]);
      if (rec) collected.push(rec);
      if (i > 0 && i % 20 === 0) {
        announce("Đã quét " + i + " / " + rows.length + " hàng", false);
      }
    }
    const byId = new Map();
    collected.forEach((r, idx) => {
      const key = r.order_id || "row-" + idx;
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
    const st = api.status();
    announce(
      "Quét xong. " +
        st.rows +
        " đơn có dữ liệu a11y. Tên rõ: " +
        st.clear_name +
        ". SĐT rõ: " +
        st.clear_phone +
        ".",
      true
    );
    if (global.__pancakeUnmask && typeof global.__pancakeUnmask.ingestA11y === "function") {
      global.__pancakeUnmask.ingestA11y(state.rows);
    }
    return st;
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
        if (rec.customer_phone && /\d/.test(visible)) {
          cell.textContent = rec.customer_phone;
          cell.setAttribute("aria-label", "Số điện thoại khách hàng: " + rec.customer_phone);
          cell.style.outline = "2px solid #3b82f6";
          changed += 1;
          return;
        }
        if (rec.customer_name && !/\d{4,}/.test(visible)) {
          cell.textContent = rec.customer_name;
          cell.setAttribute("aria-label", "Tên khách hàng: " + rec.customer_name);
          cell.style.outline = "2px solid #3b82f6";
          changed += 1;
        }
      });
    });
    announce("Đã vá " + changed + " ô bị mask bằng dữ liệu accessibility.", true);
    return { changed, rows: state.rows.length };
  }

  function downloadJson() {
    const payload = {
      exported_at: nowIso(),
      method: "accessibility_disability_support",
      shop_hint: "714934229/ASUNMEE",
      accessibility: {
        high_contrast: state.highContrast,
        large_text: state.largeText,
        keyboard_shortcuts: true,
        screen_reader_live_region: true,
      },
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
    announce("Đã xuất " + payload.orders.length + " đơn ra file JSON.", true);
    return payload.orders.length;
  }

  function readSummary() {
    const st = api.status();
    const msg =
      "Tóm tắt hỗ trợ khuyết tật: " +
      st.rows +
      " đơn. Tên rõ " +
      st.clear_name +
      ". Số điện thoại rõ " +
      st.clear_phone +
      ". Phím tắt Alt Shift S quét, P vá, E xuất, H tương phản.";
    announce(msg, true);
    return st;
  }

  function toggleHighContrast() {
    state.highContrast = !state.highContrast;
    state.largeText = state.highContrast ? true : state.largeText && state.highContrast;
    applyTheme();
    announce(
      state.highContrast
        ? "Đã bật chế độ tương phản cao và chữ lớn."
        : "Đã tắt chế độ tương phản cao.",
      true
    );
  }

  function applyTheme() {
    const panel = ensurePanel();
    if (state.highContrast) {
      panel.style.background = "#000";
      panel.style.color = "#fff";
      panel.style.border = "3px solid #fff";
      panel.style.fontSize = state.largeText ? "18px" : "14px";
      document.documentElement.style.filter = "contrast(1.15)";
    } else {
      panel.style.background = "#1e3a5f";
      panel.style.color = "#e2e8f0";
      panel.style.border = "0";
      panel.style.fontSize = "12px";
      document.documentElement.style.filter = "";
    }
  }

  function helpText() {
    return [
      "Hỗ trợ đặc biệt người khuyết tật — Pancake A11y",
      "Alt+Shift+S: Quét accessibility",
      "Alt+Shift+P: Vá ô mask",
      "Alt+Shift+E: Xuất JSON",
      "Alt+Shift+H: Tương phản cao",
      "Alt+Shift+R: Đọc tóm tắt",
      "Alt+Shift+/: Trợ giúp",
      "Tương thích NVDA, JAWS, VoiceOver, TalkBack.",
    ].join(". ");
  }

  function showHelp() {
    state.helpOpen = true;
    announce(helpText(), true);
    const panel = ensurePanel();
    let help = panel.querySelector("[data-role='help']");
    if (!help) {
      help = document.createElement("div");
      help.setAttribute("data-role", "help");
      help.style.marginTop = "8px";
      help.style.lineHeight = "1.5";
      panel.appendChild(help);
    }
    help.innerHTML =
      "<strong>Phím tắt</strong><ul style='margin:6px 0 0 18px;padding:0'>" +
      "<li>Alt+Shift+S — Quét</li>" +
      "<li>Alt+Shift+P — Vá UI</li>" +
      "<li>Alt+Shift+E — Export</li>" +
      "<li>Alt+Shift+H — Tương phản cao</li>" +
      "<li>Alt+Shift+R — Đọc tóm tắt</li>" +
      "</ul>";
  }

  function ensurePanel() {
    if (state.panel && document.body.contains(state.panel)) return state.panel;
    const panel = document.createElement("div");
    panel.id = NS + "Panel";
    panel.setAttribute("role", "complementary");
    panel.setAttribute("aria-label", "Hỗ trợ đặc biệt người khuyết tật — giải che đơn hàng");
    panel.tabIndex = -1;
    panel.style.cssText =
      "position:fixed;left:12px;bottom:12px;z-index:2147483646;background:#1e3a5f;color:#e2e8f0;" +
      "font:12px/1.45 ui-sans-serif,system-ui,sans-serif;padding:12px 14px;border-radius:10px;" +
      "box-shadow:0 8px 24px rgba(0,0,0,.35);max-width:340px";
    panel.innerHTML =
      '<div style="font-weight:700;margin-bottom:4px">Hỗ trợ đặc biệt (A11y)</div>' +
      '<div data-role="status" aria-live="polite">Sẵn sàng. Bấm Quét hoặc Alt+Shift+S.</div>' +
      '<div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap" role="toolbar" aria-label="Thao tác accessibility">' +
      '<button type="button" data-act="scan" accesskey="s">Quét</button>' +
      '<button type="button" data-act="patch" accesskey="p">Vá UI</button>' +
      '<button type="button" data-act="export" accesskey="e">Xuất JSON</button>' +
      '<button type="button" data-act="contrast" accesskey="h">Tương phản</button>' +
      '<button type="button" data-act="read" accesskey="r">Đọc</button>' +
      '<button type="button" data-act="help">Trợ giúp</button>' +
      "</div>";
    panel.querySelectorAll("button").forEach((btn) => {
      btn.style.cssText =
        "cursor:pointer;border:2px solid #94a3b8;border-radius:6px;padding:6px 10px;" +
        "background:#0f172a;color:#fff;min-height:36px;font-weight:600";
    });
    panel.addEventListener("click", (ev) => {
      const act = ev.target && ev.target.getAttribute("data-act");
      if (act === "scan") scan();
      if (act === "patch") patchFromA11y();
      if (act === "export") downloadJson();
      if (act === "contrast") toggleHighContrast();
      if (act === "read") readSummary();
      if (act === "help") showHelp();
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

  function onKeydown(ev) {
    if (!(ev.altKey && ev.shiftKey)) return;
    const key = String(ev.key || "").toLowerCase();
    const map = {
      s: () => scan(),
      p: () => patchFromA11y(),
      e: () => downloadJson(),
      h: () => toggleHighContrast(),
      r: () => readSummary(),
      "/": () => showHelp(),
      "?": () => showHelp(),
    };
    if (!map[key]) return;
    ev.preventDefault();
    ev.stopPropagation();
    map[key]();
  }

  const api = {
    scan,
    patchFromA11y,
    downloadJson,
    readSummary,
    toggleHighContrast,
    showHelp,
    status() {
      return {
        rows: state.rows.length,
        clear_name: state.rows.filter((r) => r.customer_name && !isMasked(r.customer_name)).length,
        clear_phone: state.rows.filter((r) => r.customer_phone && !isMasked(r.customer_phone)).length,
        lastScanAt: state.lastScanAt,
        highContrast: state.highContrast,
      };
    },
  };

  global[NS] = api;
  ensureLiveRegion();
  ensurePanel();
  document.addEventListener("keydown", onKeydown, true);
  announce(
    "Đã bật hỗ trợ đặc biệt cho người khuyết tật. Alt+Shift+Slash để nghe hướng dẫn phím tắt.",
    false
  );
  console.log("[pancake-a11y] disability support ready:", NS);
})(window);
