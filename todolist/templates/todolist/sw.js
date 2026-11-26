/* Todo list service worker: shows push notifications and opens the right page when one is tapped.
   It doesn't cache pages, so the app always shows fresh data. */
"use strict";
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (event) { event.waitUntil(self.clients.claim()); });

self.addEventListener("push", function (event) {
  var data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { body: event.data && event.data.text() }; }
  var title = data.title || "Todo list";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    tag: data.tag || undefined,
    icon: "{{ icon }}",
    badge: "{{ badge }}",
    data: { url: data.url || "{{ home }}" }
  }));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var url = new URL((event.notification.data && event.notification.data.url) || "{{ home }}", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (list) {
    for (var i = 0; i < list.length; i++) {
      if ("focus" in list[i]) { list[i].navigate(url).catch(function () {}); return list[i].focus(); }
    }
    return self.clients.openWindow(url);
  }));
});
