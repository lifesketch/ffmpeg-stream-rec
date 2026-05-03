(function () {
  var url = window.LIVE_STATUS_URL;
  if (!url) return;

  function fmtSize(bytes) {
    if (bytes == null || bytes === 0) return "0.00 MB";
    var mb = bytes / (1024 * 1024);
    if (mb < 0.01) return (bytes / 1024).toFixed(1) + " KB";
    return mb.toFixed(2) + " MB";
  }

  function tick() {
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        var sessions = data.sessions || [];
        var active = 0;
        sessions.forEach(function (s) {
          var tr = document.querySelector('tr[data-session-id="' + s.id + '"]');
          if (!tr) return;
          var ind = tr.querySelector(".rec-indicator");
          var sz = tr.querySelector(".live-file-size");
          var stLabel = tr.querySelector(".status-text");
          var endCell = tr.querySelector(".ended-at-cell");
          if (s.status === "recording") {
            active++;
            tr.classList.add("session-recording");
            if (ind) ind.hidden = false;
            if (stLabel) {
              stLabel.textContent = "Запись";
              stLabel.classList.add("status-text--live");
            }
            if (sz)
              sz.textContent = fmtSize(
                s.current_file_bytes != null ? s.current_file_bytes : 0
              );
            if (endCell) endCell.textContent = "—";
          } else {
            tr.classList.remove("session-recording");
            if (ind) ind.hidden = true;
            if (stLabel) {
              stLabel.textContent = s.status;
              stLabel.classList.remove("status-text--live");
            }
            if (sz) sz.textContent = "—";
            if (endCell)
              endCell.textContent =
                s.ended_at_local || (s.ended_at ? s.ended_at : "—");
          }
        });

        var banner = document.getElementById("recording-banner");
        if (banner) {
          if (active > 0) {
            banner.hidden = false;
            banner.classList.add("recording-banner--on");
            var bc = banner.querySelector(".recording-banner__count");
            if (bc) bc.textContent = "Активных сессий: " + active;
          } else {
            banner.hidden = true;
            banner.classList.remove("recording-banner--on");
          }
        }

        document.body.classList.toggle("has-active-recording", active > 0);
      })
      .catch(function () {});
  }

  setInterval(tick, 1500);
  tick();
})();
