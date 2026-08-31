document.addEventListener("DOMContentLoaded", function () {

  /* ---- salin tautan halaman status ---- */
  const copyBtn = document.getElementById("copy-url");
  const urlInput = document.getElementById("status-url");
  if (copyBtn && urlInput) {
    copyBtn.addEventListener("click", function () {
      urlInput.select();
      urlInput.setSelectionRange(0, 99999);   // untuk peramban di ponsel
      const done = function () {
        copyBtn.textContent = "Tersalin";
        setTimeout(function () { copyBtn.textContent = "Salin"; }, 1800);
      };
      if (navigator.clipboard) {
        navigator.clipboard.writeText(urlInput.value).then(done, function () {
          document.execCommand("copy"); done();
        });
      } else {
        document.execCommand("copy"); done();
      }
    });
  }

  /* ---- lanjutkan pembayaran yang belum selesai ---- */
  const payBtn = document.getElementById("pay-again");
  if (!payBtn) return;
  const errBox = document.getElementById("pay-error");
  const orderId = window.location.pathname.split("/").pop();

  function showError(msg) {
    if (!errBox) return;
    errBox.textContent = msg;
    errBox.style.display = "block";
  }

  payBtn.addEventListener("click", async function () {
    if (errBox) errBox.style.display = "none";
    payBtn.disabled = true;
    payBtn.textContent = "Memproses...";

    try {
      const res = await fetch("/api/pay/" + orderId, { method: "POST" });
      const data = await res.json();

      if (!res.ok) {
        showError(data.error || "Tidak dapat membuka pembayaran.");
        payBtn.disabled = false;
        payBtn.textContent = "Lanjutkan pembayaran";
        return;
      }

      if (typeof window.snap === "undefined") {
        showError("Modul pembayaran belum dimuat. Muat ulang halaman lalu coba lagi.");
        payBtn.disabled = false;
        payBtn.textContent = "Lanjutkan pembayaran";
        return;
      }

      // Nomor pendaftaran tetap; cukup muat ulang halaman yang sama
      const target = "/status/" + data.order_id;

      window.snap.pay(data.snap_token, {
        onSuccess: function () { window.location.href = target; },
        onPending: function () { window.location.href = target; },
        onError: function () {
          showError("Pembayaran gagal diproses. Silakan coba lagi.");
          payBtn.disabled = false;
          payBtn.textContent = "Lanjutkan pembayaran";
        },
        onClose: function () {
          payBtn.disabled = false;
          payBtn.textContent = "Lanjutkan pembayaran";
        },
      });
    } catch (err) {
      showError("Tidak dapat terhubung ke server. Periksa koneksi Anda.");
      payBtn.disabled = false;
      payBtn.textContent = "Lanjutkan pembayaran";
    }
  });
});
