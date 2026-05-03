(function () {
  var dlg = document.getElementById("history-dialog");
  var btnOpen = document.getElementById("btn-history-open");
  var btnClose = document.getElementById("history-close");
  var btnRepeat = document.getElementById("history-repeat");
  var btnDel = document.getElementById("history-delete");
  var loading = document.getElementById("history-loading");
  var table = document.getElementById("history-table");
  var tbody = table ? table.querySelector("tbody") : null;

  function escapeHtml(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function tplUrl(tmpl, id) {
    return tmpl.replace("__HID__", id);
  }

  function loadHistory() {
    var url = window.HISTORY_API_URL;
    if (!url || !tbody || !loading || !table) return;
    loading.hidden = false;
    loading.textContent = "Загрузка…";
    table.hidden = true;
    tbody.innerHTML = "";
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        loading.hidden = true;
        var items = data.items || [];
        if (items.length === 0) {
          loading.hidden = false;
          loading.textContent = "История пуста. Запустите запись с главной формы.";
          return;
        }
        table.hidden = false;
        items.forEach(function (row) {
          var tr = document.createElement("tr");
          tr.innerHTML =
            '<td><input type="radio" name="hist_pick" value="' +
            escapeHtml(row.id) +
            '"></td>' +
            '<td class="mono small">' +
            escapeHtml(row.added_at_local || row.added_at) +
            "</td>" +
            '<td class="small history-url">' +
            escapeHtml(row.stream_url) +
            "</td>" +
            "<td>" +
            escapeHtml(row.basename) +
            "</td>" +
            "<td>" +
            escapeHtml(row.storage_mode) +
            "</td>" +
            "<td class=\"mono small\">" +
            escapeHtml(row.subpath || "—") +
            "</td>";
          tbody.appendChild(tr);
        });
      })
      .catch(function () {
        loading.hidden = false;
        loading.textContent = "Не удалось загрузить историю.";
      });
  }

  function selectedId() {
    var el = document.querySelector(
      '#history-dialog input[name="hist_pick"]:checked'
    );
    return el ? el.value : null;
  }

  function postTo(url) {
    var f = document.createElement("form");
    f.method = "POST";
    f.action = url;
    document.body.appendChild(f);
    f.submit();
  }

  if (btnOpen && dlg) {
    btnOpen.addEventListener("click", function () {
      loadHistory();
      if (typeof dlg.showModal === "function") dlg.showModal();
    });
  }
  if (btnClose && dlg) {
    btnClose.addEventListener("click", function () {
      dlg.close();
    });
  }
  if (btnRepeat) {
    btnRepeat.addEventListener("click", function () {
      var id = selectedId();
      if (!id) {
        alert("Выберите строку в таблице.");
        return;
      }
      postTo(tplUrl(window.HISTORY_REPEAT_TMPL || "", id));
    });
  }
  if (btnDel) {
    btnDel.addEventListener("click", function () {
      var id = selectedId();
      if (!id) {
        alert("Выберите строку в таблице.");
        return;
      }
      if (!confirm("Удалить выбранную запись из истории?")) return;
      postTo(tplUrl(window.HISTORY_DELETE_TMPL || "", id));
    });
  }
})();
