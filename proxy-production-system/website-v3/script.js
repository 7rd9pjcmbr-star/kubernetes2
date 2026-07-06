const yearEl = document.getElementById("year");
const form = document.querySelector(".cta-form");
const message = document.getElementById("form-message");
const metricOrders = document.getElementById("metric-orders");

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
