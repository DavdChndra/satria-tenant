document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("registration-form");
  const submitBtn = document.getElementById("submit-btn");
  const errorBox = document.getElementById("form-error");
  const totalBox = document.getElementById("reg-total");
  const totalValue = document.getElementById("reg-total-value");
  const summaryEmpty = document.getElementById("reg-summary-empty");
  const summaryBody = document.getElementById("reg-summary-body");
  const summaryBooth = document.getElementById("reg-summary-booth");
  const summaryAddonRow = document.getElementById("reg-summary-addon-row");
  const summaryAddons = document.getElementById("reg-summary-addons");
  const summaryTotal = document.getElementById("reg-summary-total");

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
    const boothInput = form.querySelector('input[name="booth_type_id"]:checked');
    if (!boothInput) {
      if (totalBox) totalBox.hidden = true;
      if (summaryEmpty) summaryEmpty.hidden = false;
      if (summaryBody) summaryBody.hidden = true;
      return;
    }
    const boothOption = boothInput.closest(".booth-option");
    const boothPrice = parseInt(boothOption.querySelector(".booth-price").dataset.price || "0", 10);
    const boothName = boothOption.querySelector(".booth-name").textContent;

    const selectedAddonNames = [];
    let total = boothPrice;
    addonRows.forEach(function (row) {
      if (row.querySelector(".addon-toggle-btn").getAttribute("aria-pressed") === "true") {
        total += parseInt(row.dataset.addonPrice || "0", 10);
        const name = row.querySelector(".addon-row-name");
        if (name) selectedAddonNames.push(name.textContent);
      }
    });

    if (totalBox) {
      totalValue.textContent = formatRupiah(total);
      totalBox.hidden = false;
    }

    if (summaryBody) {
      summaryEmpty.hidden = true;
      summaryBody.hidden = false;
      summaryBooth.textContent = boothName;
      if (selectedAddonNames.length) {
        summaryAddonRow.hidden = false;
        summaryAddons.textContent = selectedAddonNames.join(", ");
      } else {
        summaryAddonRow.hidden = true;
      }
      summaryTotal.textContent = formatRupiah(total);
    }
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
        onSuccess: async function () {
          await goToTicketWhenPaid(data.order_id);
        },
        onPending: function () {
          window.location.href = "/status/" + data.order_id;
        },
        onError: function () {
          showError("Pembayaran gagal diproses. Silakan coba lagi.");
          setLoading(false);
        },
        onClose: function () {
          window.location.href = "/status/" + data.order_id;
        },
      });
    } catch (err) {
      showError("Tidak dapat terhubung ke server. Periksa koneksi Anda.");
      setLoading(false);
    }
  });

  async function goToTicketWhenPaid(orderId) {
    const ticketUrl = "/ticket/" + orderId;
    for (let attempt = 0; attempt < 8; attempt += 1) {
      try {
        const res = await fetch("/api/payment/" + orderId + "/confirm", { method: "POST" });
        const data = await res.json();
        if (res.ok && data.paid) {
          window.location.href = ticketUrl;
          return;
        }
      } catch (err) {
        // Continue retrying while the Midtrans notification is being processed.
      }
      await new Promise(function (resolve) { setTimeout(resolve, 1000); });
    }
    window.location.href = "/status/" + orderId;
  }
});
