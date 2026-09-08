document.addEventListener("DOMContentLoaded", function () {
  const bg = document.getElementById("hero-photo-bg");
  if (!bg) return;

  const slides = Array.from(bg.querySelectorAll(".hero-photo-slide"));
  const total = slides.length;
  if (total <= 1) return;

  let index = 0;
  const INTERVAL = 6000;

  setInterval(function () {
    slides[index].classList.remove("active");
    index = (index + 1) % total;
    slides[index].classList.add("active");
  }, INTERVAL);
});
