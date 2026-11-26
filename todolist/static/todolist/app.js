/* Shared behaviour for task lists: mark done, filters, tabs, and highlighting a just-saved task. */
(function () {
  "use strict";
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";

  // Tick / untick a task. On failure the checkbox goes back and the user is told.
  window.toggle_status = function (id, box) {
    var body = new URLSearchParams({ id: id });
    fetch("/todolist/ajax/update_item_status", { method: "POST", body: body, credentials: "same-origin",
                                                 headers: { "X-CSRFToken": csrf } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function () { var li = box.closest("li.task"); if (li) li.classList.toggle("done", box.checked); })
      .catch(function () { box.checked = !box.checked; alert("Could not update the task. Reload the page and try again."); });
  };

  function onReady(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }

  onReady(function () {
    // Filters (task list only): project, priority, tag and search combine.
    var f = { project: document.getElementById("filter-project"), priority: document.getElementById("filter-priority"),
              tag: document.getElementById("filter-tag"), text: document.getElementById("filter-text") };
    function applyFilters() {
      var prio = f.priority ? f.priority.value : "0", tag = f.tag ? f.tag.value : "", project = f.project ? f.project.value : "";
      var text = f.text ? f.text.value.toLowerCase().trim() : "";
      document.querySelectorAll(".task-list").forEach(function (list) {
        var shown = 0, total = 0;
        list.querySelectorAll("li.task").forEach(function (li) {
          var tags = (li.dataset.tags || "").split(",").map(function (t) { return t.trim(); });
          var ok = (prio === "0" || li.dataset.priority === prio) && (!project || li.dataset.project === project)
                && (!tag || tags.indexOf(tag) !== -1) && (!text || (li.dataset.text || "").indexOf(text) !== -1);
          li.hidden = !ok; total++; if (ok) shown++;
        });
        var empty = list.querySelector(".filtered-empty");
        if (empty) empty.hidden = !(total > 0 && shown === 0);
      });
    }
    if (f.priority) {
      // Browsers (notably Safari) can restore old filter values; always start unfiltered.
      f.priority.value = "0"; if (f.tag) f.tag.value = ""; if (f.project) f.project.value = ""; if (f.text) f.text.value = "";
      ["project", "priority", "tag"].forEach(function (k) { if (f[k]) f[k].addEventListener("change", applyFilters); });
      if (f.text) f.text.addEventListener("input", applyFilters);
    }

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
