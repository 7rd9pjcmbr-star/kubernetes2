const yearEl = document.getElementById("year");
const form = document.querySelector(".cta-form");
const message = document.getElementById("form-message");

if (yearEl) {
  yearEl.textContent = String(new Date().getFullYear());
}

if (form && message) {
  form.addEventListener("submit", () => {
    message.textContent = "Đã nhận thông tin. Team sales sẽ liên hệ trong 1 ngày làm việc.";
  });
}
