const yearEl = document.getElementById("year");
const form = document.querySelector(".cta-form");
const message = document.getElementById("form-message");

if (yearEl) {
  yearEl.textContent = String(new Date().getFullYear());
}

if (form && message) {
  form.addEventListener("submit", () => {
    message.textContent =
      "Đã nhận email. Blueprint kế hoạch kinh doanh sẽ được gửi trong 1 ngày làm việc.";
  });
}

const revealTargets = document.querySelectorAll(
  ".section h2, .signal-list, .value-rail, .persona-stack, .pricing-rail, .cost-meter, .steps, .table-wrap, .roadmap, .risk-list, .cta-panel"
);

revealTargets.forEach((el) => el.classList.add("reveal"));

if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.16, rootMargin: "0px 0px -8% 0px" }
  );

  revealTargets.forEach((el) => observer.observe(el));
} else {
  revealTargets.forEach((el) => el.classList.add("is-visible"));
}
