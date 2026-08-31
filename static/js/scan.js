document.addEventListener("DOMContentLoaded", function () {
  const video = document.getElementById("scan-video");
  const startBtn = document.getElementById("scan-start");
  const stopBtn = document.getElementById("scan-stop");
  const hint = document.getElementById("scan-hint");
  const result = document.getElementById("scan-result");
  const viewport = document.getElementById("scan-viewport");
  if (!video || !startBtn) return;

  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });

  let stream = null;
  let scanning = false;
  let lastToken = "";
  let lastAt = 0;
  let busy = false;

  function render(state, data) {
    const map = {
      ok: ["scan-ok", "&#10003;", "Validasi berhasil"],
      repeat: ["scan-warn", "&#8635;", "Sudah pernah masuk"],
      unpaid: ["scan-warn", "&#33;", "Belum lunas"],
      invalid: ["scan-bad", "&#10005;", "Kartu tidak sah"],
      error: ["scan-bad", "&#10005;", "Gagal memvalidasi"],
    };
    const [cls, icon, title] = map[state] || map.error;

    let detail = "";
    if (data && data.institution) {
      detail = '<div class="scan-detail">' +
        '<span class="scan-inst">' + data.institution + "</span>" +
        (data.pic ? '<span class="scan-sub">' + data.pic + "</span>" : "") +
        (data.booth ? '<span class="scan-sub">' + data.booth + "</span>" : "") +
        (data.order_id ? '<span class="scan-sub mono">' + data.order_id + "</span>" : "") +
        (data.checked_in_at ? '<span class="scan-time">Masuk ' + data.checked_in_at + "</span>" : "") +
        "</div>";
    }

    result.innerHTML =
      '<div class="scan-card ' + cls + '">' +
        '<span class="scan-icon">' + icon + "</span>" +
        '<span class="scan-title">' + title + "</span>" +
        '<p class="scan-msg">' + ((data && data.message) || "") + "</p>" +
        detail +
      "</div>";

    // getar singkat sebagai penanda di ponsel
    if (navigator.vibrate) navigator.vibrate(state === "ok" ? 60 : [40, 60, 40]);
  }

  async function verify(token) {
    busy = true;
    try {
      const res = await fetch("/admin/scan/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: token }),
      });
      const data = await res.json();
      render(data.status || "error", data);
    } catch (err) {
      render("error", { message: "Tidak dapat terhubung ke server." });
    } finally {
      // jeda agar kartu yang sama tidak dipindai berulang-ulang
      setTimeout(function () { busy = false; }, 1500);
    }
  }

  function tick() {
    if (!scanning) return;

    if (video.readyState === video.HAVE_ENOUGH_DATA && !busy) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const code = window.jsQR
        ? jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" })
        : null;

      if (code && code.data) {
        const now = Date.now();
        // kode sama diabaikan bila baru saja diproses
        if (code.data !== lastToken || now - lastAt > 3000) {
          lastToken = code.data;
          lastAt = now;
          verify(code.data);
        }
      }
    }
    requestAnimationFrame(tick);
  }

  async function start() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      hint.textContent = "Peramban ini tidak mendukung akses kamera.";
      hint.classList.add("scan-hint-bad");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },   // kamera belakang bila ada
        audio: false,
      });
      video.srcObject = stream;
      await video.play();

      scanning = true;
      viewport.classList.add("is-live");
      startBtn.hidden = true;
      stopBtn.hidden = false;
      hint.textContent = "Arahkan kamera ke kode QR pada kartu peserta.";
      hint.classList.remove("scan-hint-bad");
      requestAnimationFrame(tick);
    } catch (err) {
      hint.textContent =
        "Kamera tidak dapat diakses. Pastikan izin diberikan dan halaman dibuka lewat HTTPS atau localhost.";
      hint.classList.add("scan-hint-bad");
    }
  }

  function stop() {
    scanning = false;
    if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    stream = null;
    video.srcObject = null;
    viewport.classList.remove("is-live");
    startBtn.hidden = false;
    stopBtn.hidden = true;
    hint.textContent = "Kamera dimatikan.";
  }

  startBtn.addEventListener("click", start);
  stopBtn.addEventListener("click", stop);
  window.addEventListener("pagehide", stop);
});
