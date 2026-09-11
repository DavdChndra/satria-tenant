document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("registration-form-peserta");
  if (!form) return;
  const submitBtn = document.getElementById("submit-btn");
  const errorBox = document.getElementById("form-error");
  const totalBox = document.getElementById("reg-total");
  const totalValue = document.getElementById("reg-total-value");
  const summaryEmpty = document.getElementById("reg-summary-empty");
  const summaryBody = document.getElementById("reg-summary-body");
  const summaryBooth = document.getElementById("reg-summary-booth");
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

  function updateTotal() {
    const input = form.querySelector('input[name="participant_type_id"]:checked');
    if (!input) {
      if (totalBox) totalBox.hidden = true;
      if (summaryEmpty) summaryEmpty.hidden = false;
      if (summaryBody) summaryBody.hidden = true;
      return;
    }
    const option = input.closest(".booth-option");
    const price = parseInt(option.querySelector(".booth-price").dataset.price || "0", 10);
    const name = option.querySelector(".booth-name").textContent;

    if (totalBox) {
      totalValue.textContent = formatRupiah(price);
      totalBox.hidden = false;
    }
    if (summaryBody) {
      summaryEmpty.hidden = true;
      summaryBody.hidden = false;
      summaryBooth.textContent = name;
      summaryTotal.textContent = formatRupiah(price);
    }
  }

  form.querySelectorAll('input[name="participant_type_id"]').forEach(function (radio) {
    radio.addEventListener("change", updateTotal);
  });

  updateTotal();

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    hideError();

    const input = form.querySelector('input[name="participant_type_id"]:checked');
    if (!input) {
      showError("Pilih salah satu paket peserta terlebih dahulu.");
      return;
    }

    const payload = {
      full_name: form.full_name.value.trim(),
      email: form.email.value.trim(),
      phone: form.phone.value.trim(),
      participant_type_id: input.value,
    };

    for (const [key, value] of Object.entries(payload)) {
      if (!value) {
        showError("Mohon lengkapi semua data sebelum melanjutkan.");
        return;
      }
    }

    setLoading(true);
    try {
      const res = await fetch("/api/register-peserta", {
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
          window.location.href = "/status-peserta/" + data.order_id;
        },
        onError: function () {
          showError("Pembayaran gagal diproses. Silakan coba lagi.");
          setLoading(false);
        },
        onClose: function () {
          window.location.href = "/status-peserta/" + data.order_id;
        },
      });
    } catch (err) {
      showError("Tidak dapat terhubung ke server. Periksa koneksi Anda.");
      setLoading(false);
    }
  });

  async function goToTicketWhenPaid(orderId) {
    const ticketUrl = "/tiket-peserta/" + orderId;
    for (let attempt = 0; attempt < 8; attempt += 1) {
      try {
        const res = await fetch("/api/payment-peserta/" + orderId + "/confirm", { method: "POST" });
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
    window.location.href = "/status-peserta/" + orderId;
  }
});
