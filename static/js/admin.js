document.addEventListener("DOMContentLoaded", function () {

  /**
   * Menonaktifkan penggeser yang tidak berpengaruh.
   *
   * object-position hanya bisa menggeser pada sumbu yang gambarnya melebihi
   * bingkai. Bila rasio gambar lebih lebar dari bingkai, yang berlebih adalah
   * sisi kiri-kanan (geser horizontal aktif); bila lebih tinggi, yang berlebih
   * sisi atas-bawah. Tanpa penanda ini admin bingung karena penggeser
   * tampak tidak melakukan apa-apa.
   */
  function syncSliderAvailability(card, img, frame) {
    const rowX = card.querySelector('input[name="pos_x"]');
    const rowY = card.querySelector('input[name="pos_y"]');
    if (!img || !img.naturalWidth || !frame) return;

    const imgRatio = img.naturalWidth / img.naturalHeight;
    const frameRatio = frame.offsetWidth / frame.offsetHeight;
    if (!frameRatio) return;

    // toleransi kecil agar rasio yang nyaris sama tidak dianggap bisa digeser
    const canX = imgRatio > frameRatio * 1.02;
    const canY = imgRatio < frameRatio * 0.98;

    [[rowX, canX], [rowY, canY]].forEach(function (pair) {
      const input = pair[0], usable = pair[1];
      if (!input) return;
      const row = input.closest(".pos-row");
      input.disabled = !usable;
      if (row) row.classList.toggle("pos-row-off", !usable);
    });

    const note = card.querySelector(".pos-note");
    if (note) {
      if (!canX && !canY) {
        note.textContent = "Gambar sudah pas dengan bingkai — tidak ada bagian yang bisa digeser.";
        note.hidden = false;
      } else if (!canX) {
        note.textContent = "Gambar ini hanya bisa digeser atas–bawah.";
        note.hidden = false;
      } else if (!canY) {
        note.textContent = "Gambar ini hanya bisa digeser kiri–kanan.";
        note.hidden = false;
      } else {
        note.hidden = true;
      }
    }
  }


  /* ---- pengatur posisi gambar carousel ---- */
  document.querySelectorAll(".photo-card").forEach(function (card) {
    const preview = card.querySelector(".adjust-preview");
    const controls = card.querySelector(".pos-controls");
    const sliders = card.querySelectorAll(".pos-slider");
    const fitRadios = card.querySelectorAll('input[name="fit_mode"]');
    if (!preview) return;

    function apply() {
      const checked = card.querySelector('input[name="fit_mode"]:checked');
      const mode = checked ? checked.value : "contain";
      const x = card.querySelector('input[name="pos_x"]');
      const y = card.querySelector('input[name="pos_y"]');

      preview.style.objectFit = mode;
      preview.style.objectPosition = (x ? x.value : 50) + "% " + (y ? y.value : 50) + "%";

      // Menggeser posisi hanya berpengaruh saat gambar dipotong
      if (controls) controls.hidden = mode !== "cover";
    }

    sliders.forEach(function (sl) {
      sl.addEventListener("input", function () {
        const out = sl.parentElement.querySelector(".pos-value");
        if (out) out.textContent = sl.value + "%";
        apply();
      });
    });
    fitRadios.forEach(function (r) { r.addEventListener("change", apply); });

    function refresh() {
      syncSliderAvailability(card, preview, preview.parentElement);
    }
    if (preview.complete) refresh(); else preview.addEventListener("load", refresh);
    fitRadios.forEach(function (r) { r.addEventListener("change", refresh); });

    apply();
  });

  /* ---- posisi foto pembicara ---- */
  document.querySelectorAll(".speaker-admin-card").forEach(function (card) {
    const preview = card.querySelector(".sp-preview");
    if (!preview) return;

    const sliders = card.querySelectorAll(".pos-slider");
    sliders.forEach(function (sl) {
      sl.addEventListener("input", function () {
        const out = sl.parentElement.querySelector(".pos-value");
        if (out) out.textContent = sl.value + "%";

        const x = card.querySelector('input[name="pos_x"]');
        const y = card.querySelector('input[name="pos_y"]');
        preview.style.objectPosition =
          (x ? x.value : 50) + "% " + (y ? y.value : 50) + "%";
      });
    });

    function refreshSp() {
      syncSliderAvailability(card, preview, preview.parentElement);
    }
    if (preview.complete) refreshSp(); else preview.addEventListener("load", refreshSp);
  });

  /* ---- navbar admin: tandai bagian yang sedang dilihat ---- */
  const links = Array.from(document.querySelectorAll(".admin-nav-link"));
  if (!links.length) return;

  const targets = links
    .map(function (a) {
      const el = document.querySelector(a.getAttribute("href"));
      return el ? { link: a, el: el } : null;
    })
    .filter(Boolean);

  function markActive() {
    // Bagian aktif = yang paling dekat di atas garis 140px dari puncak layar
    let current = targets[0];
    targets.forEach(function (t) {
      if (t.el.getBoundingClientRect().top <= 140) current = t;
    });
    links.forEach(function (a) { a.classList.remove("is-active"); });
    if (current) current.link.classList.add("is-active");
  }

  let ticking = false;
  window.addEventListener("scroll", function () {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function () { markActive(); ticking = false; });
  }, { passive: true });

  markActive();
});
