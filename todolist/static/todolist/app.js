/* Shared behaviour for task lists: mark done, filters, tabs, and highlighting a just-saved task. */
(function () {
  "use strict";
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  // Tick / untick a task (#14). On failure the checkbox goes back and the user is told.
  function setStatus(id, box, done, then) {
    var body = new URLSearchParams({ id: id });
    return fetch("/todolist/ajax/update_item_status", { method: "POST", body: body, credentials: "same-origin",
                                                        headers: { "X-CSRFToken": csrf } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (data) {
        box.checked = !!data.status;
        var li = box.closest("li.task"); if (li) li.classList.toggle("done", box.checked);
        if (then) then(data);
      })
      .catch(function () { box.checked = !done; showToast("Couldn't update the task. Check your connection and try again."); });
  }

  // A short message at the bottom of the screen, with an optional action button.
  var toastTimer = null;
  function showToast(text, actionLabel, onAction) {
    var t = document.querySelector(".toast-bar");
    if (!t) {
      t = document.createElement("div");
      t.className = "toast-bar"; t.setAttribute("role", "status"); t.setAttribute("aria-live", "polite");
      document.body.appendChild(t);
    }
    t.textContent = "";
    var msg = document.createElement("span"); msg.textContent = text; t.appendChild(msg);
    if (actionLabel) {
      var b = document.createElement("button"); b.type = "button"; b.textContent = actionLabel;
      b.addEventListener("click", function () { hide(); onAction(); });
      t.appendChild(b);
    }
    t.hidden = false; t.classList.add("show");
    clearTimeout(toastTimer);
    function hide() { t.classList.remove("show"); t.hidden = true; }
    toastTimer = setTimeout(hide, 6000);
  }

  document.addEventListener("click", function (e) {
    // The 44px area around a checkbox ticks it too, without opening the task.
    var hit = e.target.closest && e.target.closest(".check-hit");
    if (hit && !e.target.matches("input")) { e.preventDefault(); hit.querySelector("input").click(); }
  });
  document.addEventListener("change", function (e) {
    var box = e.target;
    if (!box.matches || !box.matches("input.task-check")) return;
    var li = box.closest("li.task"); if (!li) return;
    var done = box.checked, title = li.querySelector(".task-title").textContent;
    setStatus(li.dataset.id, box, done, function (data) {
      if (data.status) showToast("Done: " + title, "Undo", function () { box.checked = false; setStatus(li.dataset.id, box, false); });
    });
  });

  function onReady(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }

  onReady(function () {
    // Filters (#8): search is always visible; project, priority and tag sit in a folding panel
    // and show as removable chips when set. All of them combine.
    var f = { project: document.getElementById("filter-project"), priority: document.getElementById("filter-priority"),
              tag: document.getElementById("filter-tag"), text: document.getElementById("filter-text") };
    var toggle = document.querySelector(".filter-toggle"), panel = document.getElementById("filter-panel");
    var chips = document.querySelector(".filter-chips"), countBadge = document.querySelector(".filter-count");
    function selectedLabel(sel) { return sel.options[sel.selectedIndex].text; }
    function renderChips() {
      if (!chips) return;
      chips.textContent = "";
      var active = 0;
      [["project", ""], ["priority", "0"], ["tag", ""]].forEach(function (pair) {
        var sel = f[pair[0]]; if (!sel || sel.value === pair[1]) return;
        active++;
        var b = document.createElement("button");
        b.type = "button"; b.className = "chip";
        b.setAttribute("aria-label", "Remove filter " + selectedLabel(sel));
        b.textContent = selectedLabel(sel) + " ✕";
        b.addEventListener("click", function () { sel.value = pair[1]; applyFilters(); });
        chips.appendChild(b);
      });
      if (countBadge) { countBadge.hidden = !active; countBadge.textContent = active ? " · " + active : ""; }
    }
    function applyFilters() {
      var prio = f.priority ? f.priority.value : "0", tag = f.tag ? f.tag.value : "", project = f.project ? f.project.value : "";
      var text = f.text ? f.text.value.toLowerCase().trim() : "";
      document.querySelectorAll(".tabcontent").forEach(function (tab) {
        var tabShown = 0, tabTotal = 0;
        tab.querySelectorAll(".task-list").forEach(function (list) {
          var shown = 0, total = 0;
          list.querySelectorAll("li.task").forEach(function (li) {
            var tags = (li.dataset.tags || "").split(",").map(function (t) { return t.trim(); });
            var ok = (prio === "0" || li.dataset.priority === prio) && (!project || li.dataset.project === project)
                  && (!tag || tags.indexOf(tag) !== -1) && (!text || (li.dataset.text || "").indexOf(text) !== -1);
            li.hidden = !ok; total++; if (ok) shown++;
          });
          var group = list.closest(".task-group");   // Overdue / Today heading goes when none of its tasks match
          if (group) group.hidden = total > 0 && shown === 0;
          tabShown += shown; tabTotal += total;
        });
        var empty = tab.querySelector(".filtered-empty");
        if (empty) empty.hidden = !(tabTotal > 0 && tabShown === 0);
      });
      renderChips();
    }
    if (f.priority) {
      // Browsers (notably Safari) can restore old filter values; always start unfiltered.
      f.priority.value = "0"; if (f.tag) f.tag.value = ""; if (f.project) f.project.value = ""; if (f.text) f.text.value = "";
      ["project", "priority", "tag"].forEach(function (k) { if (f[k]) f[k].addEventListener("change", applyFilters); });
      if (f.text) f.text.addEventListener("input", applyFilters);
      renderChips();
    }
    if (toggle && panel) {
      toggle.addEventListener("click", function () {
        panel.hidden = !panel.hidden;
        toggle.setAttribute("aria-expanded", String(!panel.hidden));
      });
    }

    // Quick add (#9): "More options" carries what was typed into the full form.
    var quick = document.getElementById("quick-add-text");
    var more = document.querySelector(".quick-add .more-options");
    if (quick && more) {
      more.addEventListener("click", function (e) {
        var t = quick.value.trim();
        if (t) { e.preventDefault(); location.href = more.getAttribute("href") + "?text=" + encodeURIComponent(t); }
      });
    }
    // The floating ＋ focuses the quick-add box when there is one, otherwise opens the full form.
    var fab = document.querySelector("[data-quick-add-target]");
    if (fab && quick) {
      fab.addEventListener("click", function (e) {
        e.preventDefault();
        quick.scrollIntoView({ block: "center" });
        quick.focus();
      });
    }

    // Quick due dates on the task form (#15): change the day, keep the time already set.
    var dueInput = document.querySelector('input[name="due_date"]');
    var startInput = document.querySelector('input[name="start_date"]');
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    function localDay(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
    document.querySelectorAll("[data-due-offset]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (!dueInput) return;
        var d = new Date(); d.setDate(d.getDate() + parseInt(b.dataset.dueOffset, 10));
        var time = (dueInput.value.split("T")[1] || "18:00").slice(0, 5);
        dueInput.value = localDay(d) + "T" + time;
        if (startInput && startInput.value && startInput.value > dueInput.value) startInput.value = dueInput.value;
        document.querySelectorAll("[data-due-offset]").forEach(function (o) { o.setAttribute("aria-pressed", String(o === b)); });
      });
    });

    // Pop-up menus (account #10, project ⋯ #16): one open at a time; close on Escape or a tap elsewhere.
    var menus = document.querySelectorAll("details.account, details.row-menu");
    menus.forEach(function (m) {
      m.addEventListener("toggle", function () {
        if (m.open) menus.forEach(function (o) { if (o !== m) o.open = false; });
      });
    });
    document.addEventListener("click", function (e) {
      menus.forEach(function (m) { if (m.open && !m.contains(e.target)) m.open = false; });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      menus.forEach(function (m) { if (m.open) { m.open = false; m.querySelector("summary").focus(); } });
    });

    // Tabs (task list only). Always start on Today, unless a just-saved task lives elsewhere.
    var tabs = document.querySelectorAll(".tablink");
    function openTab(name) {
      document.querySelectorAll(".tabcontent").forEach(function (el) { el.hidden = el.id !== name; });
      tabs.forEach(function (b) { var on = b.dataset.tab === name; b.classList.toggle("active", on); b.setAttribute("aria-selected", on); });
    }
    tabs.forEach(function (b) { b.addEventListener("click", function () { openTab(b.dataset.tab); }); });

    var hl = document.querySelector("[data-highlight-id]");
    var hlId = hl ? hl.dataset.highlightId : null;
    var firstTab = hl && hl.dataset.highlightTab ? hl.dataset.highlightTab : "Today";
    if (tabs.length) openTab(document.getElementById(firstTab) ? firstTab : "Today");

    if (hlId) {
      var li = document.querySelector('.tabcontent:not([hidden]) li.task[data-id="' + hlId + '"]') ||
               document.querySelector('li.task[data-id="' + hlId + '"]');
      if (li) {
        li.classList.add("just-saved");
        var d = li.querySelector("details"); if (d) d.open = true;
        li.scrollIntoView({ block: "center" });
      }
      // Drop ?added=… so a reload doesn't highlight again.
      if (window.history && history.replaceState) history.replaceState(null, "", location.pathname);
    }
  });
})();
