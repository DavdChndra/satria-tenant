document.addEventListener("DOMContentLoaded", function () {
  const overlay = document.getElementById("alur-modal");
  const openBtn = document.getElementById("alur-open");
  const closeBtn = document.getElementById("alur-close");
  const ctaBtn = document.getElementById("alur-cta");
  if (!overlay || !openBtn) return;

  const steps = Array.from(overlay.querySelectorAll(".flow-step"));
  let lastFocused = null;

  function openModal() {
    lastFocused = document.activeElement;
    overlay.hidden = false;
    document.body.style.overflow = "hidden";

    // Paksa reflow agar transisi berjalan dari keadaan awal
    void overlay.offsetWidth;
    overlay.classList.add("is-open");

    // Langkah muncul bergantian dari kiri ke kanan
    steps.forEach(function (step, i) {
      step.classList.remove("is-visible");
      setTimeout(function () { step.classList.add("is-visible"); }, 120 + i * 110);
    });

    closeBtn.focus();
  }

  function closeModal() {
    overlay.classList.remove("is-open");
    document.body.style.overflow = "";
    // Tunggu transisi selesai sebelum menyembunyikan
    setTimeout(function () {
      overlay.hidden = true;
      steps.forEach(function (s) { s.classList.remove("is-visible"); });
    }, 220);
    if (lastFocused) lastFocused.focus();
  }

  openBtn.addEventListener("click", openModal);
  closeBtn.addEventListener("click", closeModal);

  // Klik latar gelap menutup modal
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) closeModal();
  });

  // Tombol Esc menutup modal
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !overlay.hidden) closeModal();
  });

  // Tombol ajakan: tutup modal lalu gulir ke formulir
  if (ctaBtn) {
    ctaBtn.addEventListener("click", function () {
      closeModal();
      const form = document.getElementById("form-pendaftaran");
      if (form) setTimeout(function () {
        form.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 240);
    });
  }
});
