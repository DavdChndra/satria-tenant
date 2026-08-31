/**
 * Dialog konfirmasi milik aplikasi, menggantikan confirm() bawaan peramban
 * yang tampil sebagai kotak sistem ber-label alamat situs.
 */
(function () {
  const STATUS_LABEL = {
    pending: "Menunggu pembayaran",
    paid: "Lunas",
    expired: "Kedaluwarsa",
    cancelled: "Dibatalkan",
    failed: "Gagal",
    refunded: "Dana dikembalikan",
  };

  document.addEventListener("DOMContentLoaded", function () {
    const overlay = document.getElementById("confirm-modal");
    if (!overlay) return;

    const card = overlay.querySelector(".confirm-card");
    const iconEl = document.getElementById("confirm-icon");
    const titleEl = document.getElementById("confirm-title");
    const textEl = document.getElementById("confirm-text");
    const detailEl = document.getElementById("confirm-detail");
    const okBtn = document.getElementById("confirm-ok");
    const cancelBtn = document.getElementById("confirm-cancel");

    let onAccept = null;
    let lastFocused = null;

    function open(opts) {
      lastFocused = document.activeElement;
      iconEl.textContent = opts.icon || "!";
      titleEl.textContent = opts.title || "Konfirmasi";
      textEl.innerHTML = opts.text || "";

      if (opts.detail) {
        detailEl.innerHTML = opts.detail;
        detailEl.hidden = false;
      } else {
        detailEl.hidden = true;
      }

      okBtn.textContent = opts.okLabel || "Ya, lanjutkan";
      card.classList.toggle("is-danger", !!opts.danger);
      okBtn.classList.toggle("btn-danger-solid", !!opts.danger);

      onAccept = opts.onAccept || null;
      overlay.hidden = false;
      void overlay.offsetWidth;          // paksa reflow agar transisi berjalan
      overlay.classList.add("is-open");
      document.body.style.overflow = "hidden";
      cancelBtn.focus();
    }

    function close() {
      overlay.classList.remove("is-open");
      document.body.style.overflow = "";
      setTimeout(function () { overlay.hidden = true; }, 200);
      onAccept = null;
      if (lastFocused) lastFocused.focus();
    }

    okBtn.addEventListener("click", function () {
      const fn = onAccept;
      close();
      if (fn) fn();
    });
    cancelBtn.addEventListener("click", close);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !overlay.hidden) close();
    });

    /* ---- ubah status pembayaran ---- */
    document.querySelectorAll(".js-status-form").forEach(function (form) {
      const select = form.querySelector("select");
      if (!select) return;

      select.addEventListener("change", function () {
        const to = select.value;
        const from = form.dataset.current;
        if (to === from) return;

        open({
          icon: "!",
          title: "Ubah status pembayaran?",
          text: "Status pendaftaran ini akan diubah secara manual.",
          detail:
            '<div class="confirm-row"><span>No. pendaftaran</span>' +
            '<strong class="mono">' + form.dataset.order + "</strong></div>" +
            '<div class="confirm-row"><span>Status saat ini</span>' +
            "<strong>" + (STATUS_LABEL[from] || from) + "</strong></div>" +
            '<div class="confirm-row"><span>Diubah menjadi</span>' +
            '<strong class="confirm-hl">' + (STATUS_LABEL[to] || to) + "</strong></div>" +
            (to === "paid"
              ? '<p class="confirm-note">Menandai lunas akan menerbitkan kartu peserta ' +
                "dan mengirim email bukti pembayaran.</p>"
              : ""),
          okLabel: "Ya, ubah status",
          onAccept: function () { form.submit(); },
        });

        // kembalikan pilihan semula sampai admin benar-benar menyetujui
        select.value = from;
      });
    });

    /* ---- hapus pendaftaran ---- */
    document.querySelectorAll(".js-delete-form").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        open({
          icon: "\u2715",
          danger: true,
          title: "Hapus pendaftaran ini?",
          text: "Data pendaftaran akan dihapus permanen dan tidak dapat dikembalikan.",
          detail:
            '<div class="confirm-row"><span>No. pendaftaran</span>' +
            '<strong class="mono">' + form.dataset.order + "</strong></div>" +
            '<div class="confirm-row"><span>Institusi</span>' +
            "<strong>" + form.dataset.inst + "</strong></div>" +
            '<p class="confirm-note">Riwayat pembayaran di Midtrans tidak ikut terhapus. ' +
            "Bila dana perlu dikembalikan, lakukan lewat dasbor Midtrans.</p>",
          okLabel: "Ya, hapus permanen",
          onAccept: function () { form.submit(); },
        });
      });
    });
  });
})();
