document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("status-lookup-form");
  if (!form) return;
  const input = document.getElementById("status-lookup-input");

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    const orderId = input.value.trim();
    if (!orderId) return;
    window.location.href = "/status/" + encodeURIComponent(orderId);
  });
});
