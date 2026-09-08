document.addEventListener("DOMContentLoaded", function () {
  const carousel = document.getElementById("carousel");
  if (!carousel) return;

  const track = document.getElementById("carousel-track");
  const dots = Array.from(document.querySelectorAll(".carousel-dot"));
  const total = parseInt(carousel.dataset.count, 10) || 0;
  if (total <= 1) return;

  let index = 0;
  let timer = null;
  const INTERVAL = 5000;

  function render() {
    track.style.transform = "translateX(-" + index * 100 + "%)";
    dots.forEach(function (dot, i) {
      dot.classList.toggle("active", i === index);
    });
  }

  function goTo(i) {
    index = (i + total) % total;
    render();
  }

  function next() { goTo(index + 1); }
  function prev() { goTo(index - 1); }

  function startAuto() {
    stopAuto();
    timer = setInterval(next, INTERVAL);
  }

  function stopAuto() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  // Klik tombol panah — jeda putar otomatis sejenak agar tidak melompat
  document.getElementById("carousel-next").addEventListener("click", function () {
    next();
    startAuto();
  });
  document.getElementById("carousel-prev").addEventListener("click", function () {
    prev();
    startAuto();
  });

  dots.forEach(function (dot) {
    dot.addEventListener("click", function () {
      goTo(parseInt(dot.dataset.index, 10));
      startAuto();
    });
  });

  // Berhenti saat kursor di atas carousel
  carousel.addEventListener("mouseenter", stopAuto);
  carousel.addEventListener("mouseleave", startAuto);

  // Hemat sumber daya saat tab tidak aktif
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) stopAuto(); else startAuto();
  });

  // Geser dengan jari di perangkat sentuh
  let touchStartX = 0;
  carousel.addEventListener("touchstart", function (e) {
    touchStartX = e.changedTouches[0].screenX;
    stopAuto();
  }, { passive: true });

  carousel.addEventListener("touchend", function (e) {
    const delta = e.changedTouches[0].screenX - touchStartX;
    if (Math.abs(delta) > 40) { delta < 0 ? next() : prev(); }
    startAuto();
  }, { passive: true });

  render();
  startAuto();
});
