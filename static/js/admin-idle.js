(function () {
  var IDLE_LIMIT_MS = 5 * 60 * 1000;
  var timer;

  function goIdleLogout() {
    window.location.href = "/admin/idle-logout";
  }

  function resetTimer() {
    clearTimeout(timer);
    timer = setTimeout(goIdleLogout, IDLE_LIMIT_MS);
  }

  ["mousemove", "mousedown", "keydown", "scroll", "touchstart"].forEach(function (evt) {
    document.addEventListener(evt, resetTimer, { passive: true });
  });

  resetTimer();
})();
