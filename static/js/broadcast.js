document.addEventListener("DOMContentLoaded", function () {
  const picker = document.getElementById("recipient-picker");
  if (!picker) return;

  const radios = document.querySelectorAll('input[name="audience"]');
  const customRadio = document.getElementById("audience-custom");
  const boxes = Array.from(picker.querySelectorAll('input[name="tenant_ids"]'));
  const items = Array.from(picker.querySelectorAll(".picker-item"));
  const search = document.getElementById("picker-search");
  const hint = document.getElementById("picker-hint");
  const countEl = document.getElementById("picked-count");

  function updateCount() {
    countEl.textContent = boxes.filter(b => b.checked).length;
  }

  // Pemilih hanya muncul saat mode "Pilih manual" aktif
  function togglePicker() {
    picker.hidden = !customRadio.checked;
  }
  radios.forEach(r => r.addEventListener("change", togglePicker));

  boxes.forEach(b => b.addEventListener("change", updateCount));

  // Pencarian: sembunyikan baris yang tidak cocok
  if (search) {
    search.addEventListener("input", function () {
      const q = this.value.trim().toLowerCase();
      let shown = 0;
      items.forEach(function (item) {
        const match = !q || item.dataset.search.indexOf(q) !== -1;
        item.hidden = !match;
        if (match) shown++;
      });
      hint.style.display = shown === 0 ? "block" : "none";
    });
  }

  // "Pilih semua" hanya berlaku pada baris yang sedang terlihat
  const allBtn = document.getElementById("picker-all");
  const noneBtn = document.getElementById("picker-none");

  if (allBtn) allBtn.addEventListener("click", function () {
    items.forEach(function (item) {
      if (!item.hidden) item.querySelector("input").checked = true;
    });
    updateCount();
  });

  if (noneBtn) noneBtn.addEventListener("click", function () {
    boxes.forEach(b => { b.checked = false; });
    updateCount();
  });

  hint.style.display = "none";
  togglePicker();
  updateCount();
});
