document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("registration-form");
  const submitBtn = document.getElementById("submit-btn");
  const errorBox = document.getElementById("form-error");

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
    };

    for (const [key, value] of Object.entries(payload)) {
      if (key === "description") continue;   // opsional
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
