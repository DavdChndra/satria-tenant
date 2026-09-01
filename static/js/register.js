document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("registration-form");
  const submitBtn = document.getElementById("submit-btn");
  const errorBox = document.getElementById("form-error");
  const totalBox = document.getElementById("reg-total");
  const totalValue = document.getElementById("reg-total-value");

  function showError(message) {
    errorBox.textContent = message;
    errorBox.style.display = "block";
  }

  function hideError() {
    errorBox.style.display = "none";
  }

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    submitBtn.textContent = isLoading ? "Memproses..." : "Lanjutkan ke pembayaran";
  }

  function formatRupiah(value) {
    return "Rp " + value.toLocaleString("id-ID");
  }

  /* ---- opsi tambahan: tombol aktif/tidak aktif + total berjalan ---- */
  const addonRows = Array.from(form.querySelectorAll(".addon-row"));

  function selectedAddonIds() {
    return addonRows
      .filter(function (row) { return row.querySelector(".addon-toggle-btn").getAttribute("aria-pressed") === "true"; })
      .map(function (row) { return row.dataset.addonId; });
  }

  function updateTotal() {
    if (!totalBox) return;
    const boothInput = form.querySelector('input[name="booth_type_id"]:checked');
    if (!boothInput) {
      totalBox.hidden = true;
      return;
    }
    const boothPrice = parseInt(boothInput.closest(".booth-option").querySelector(".booth-price").dataset.price || "0", 10);
    let total = boothPrice;
    addonRows.forEach(function (row) {
      if (row.querySelector(".addon-toggle-btn").getAttribute("aria-pressed") === "true") {
        total += parseInt(row.dataset.addonPrice || "0", 10);
      }
    });
    totalValue.textContent = formatRupiah(total);
    totalBox.hidden = false;
  }

  form.querySelectorAll('input[name="booth_type_id"]').forEach(function (radio) {
    radio.addEventListener("change", updateTotal);
  });

  addonRows.forEach(function (row) {
    const btn = row.querySelector(".addon-toggle-btn");
    btn.addEventListener("click", function () {
      const active = btn.getAttribute("aria-pressed") === "true";
      btn.setAttribute("aria-pressed", String(!active));
      btn.classList.toggle("is-active", !active);
      btn.textContent = !active ? "Diikutkan" : "Tidak diikutkan";
      row.classList.toggle("is-active", !active);
      updateTotal();
    });
  });

  updateTotal();

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    hideError();

    const boothInput = form.querySelector('input[name="booth_type_id"]:checked');
    if (!boothInput) {
      showError("Pilih salah satu jenis booth terlebih dahulu.");
      return;
    }

    const payload = {
      institution_name: form.institution_name.value.trim(),
      pic_name: form.pic_name.value.trim(),
      email: form.email.value.trim(),
      phone: form.phone.value.trim(),
      booth_type_id: boothInput.value,
      description: form.description.value.trim(),
      add_on_ids: selectedAddonIds(),
    };

    for (const [key, value] of Object.entries(payload)) {
      if (key === "description" || key === "add_on_ids") continue;   // opsional
      if (!value) {
        showError("Mohon lengkapi semua data sebelum melanjutkan.");
        return;
      }
    }

    setLoading(true);
    try {
      const res = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || "Terjadi kesalahan. Coba lagi.");
        setLoading(false);
        return;
      }

      if (typeof window.snap === "undefined") {
        showError("Modul pembayaran belum dimuat. Muat ulang halaman lalu coba lagi.");
        setLoading(false);
        return;
      }

      window.snap.pay(data.snap_token, {
        onSuccess: function () {
          window.location.href = "/status/" + data.order_id;
        },
        onPending: function () {
          window.location.href = "/status/" + data.order_id;
        },
        onError: function () {
          showError("Pembayaran gagal diproses. Silakan coba lagi.");
          setLoading(false);
        },
        onClose: function () {
          setLoading(false);
        },
      });
    } catch (err) {
      showError("Tidak dapat terhubung ke server. Periksa koneksi Anda.");
      setLoading(false);
    }
  });
});
