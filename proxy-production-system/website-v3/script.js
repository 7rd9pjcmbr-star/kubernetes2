const yearEl = document.getElementById("year");
const form = document.querySelector(".cta-form");
const message = document.getElementById("form-message");
const metricOrders = document.getElementById("metric-orders");
const apiTable = document.getElementById("platform-api-table");
const apiUpdated = document.getElementById("platform-api-updated");

const platformApiStatus = [
  {
    platform: "Pancake POS",
    endpoint: "https://pos.pages.fm/api/v1/shops",
    http: "200",
    result: "Can ket noi. API yeu cau access_token (bao loi nghiep vu ky vong).",
    level: "ok",
  },
  {
    platform: "GHTK",
    endpoint: "https://services.giaohangtietkiem.vn/services/authenticated",
    http: "401",
    result: "Can ket noi. API yeu cau Token va X-Client-Source.",
    level: "ok",
  },
  {
    platform: "Nhanh.vn POS v3",
    endpoint: "https://pos.open.nhanh.vn/v3.0/product/list",
    http: "200",
    result: "Can ket noi. Tra ERR_INVALID_APP_ID khi thieu appId/businessId.",
    level: "ok",
  },
  {
    platform: "Sapo",
    endpoint: "https://support.sapo.vn/oauth",
    http: "200/403",
    result: "Portal OAuth co the tra 403 theo IP edge firewall. API thuc te can domain shop + access token.",
    level: "warning",
  },
  {
    platform: "Haravan",
    endpoint: "https://apis.haravan.com/com/shop.json",
    http: "401",
    result: "Can ket noi. API yeu cau Authorization: Bearer <token>.",
    level: "ok",
  },
];

if (yearEl) {
  yearEl.textContent = String(new Date().getFullYear());
}

if (metricOrders) {
  const baseValue = 463561;
  const randomBump = Math.floor(Math.random() * 250);
  metricOrders.textContent = (baseValue + randomBump).toLocaleString("en-US");
}

if (form && message) {
  form.addEventListener("submit", () => {
    message.textContent = "Da gui yeu cau. Checklist rollout V3 se duoc gui toi email da dang ky.";
  });
}

if (apiTable) {
  apiTable.innerHTML = platformApiStatus
    .map((item) => {
      const badgeClass =
        item.level === "ok"
          ? "badge badge-ok"
          : item.level === "warning"
            ? "badge badge-warning"
            : "badge badge-error";
      const badgeText =
        item.level === "ok" ? "READY" : item.level === "warning" ? "NEED CONFIG" : "ERROR";

      return `
        <tr>
          <td>${item.platform}</td>
          <td class="mono">${item.endpoint}</td>
          <td class="mono">${item.http}</td>
          <td><span class="${badgeClass}">${badgeText}</span> ${item.result}</td>
        </tr>
      `;
    })
    .join("");
}

if (apiUpdated) {
  apiUpdated.textContent = "Cap nhat lan cuoi: 2026-07-06 05:06 UTC";
}
