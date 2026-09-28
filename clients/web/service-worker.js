const CACHE_NAME = "astro-shell-v10";
const APP_SHELL = [
  "/",
  "/manifest.webmanifest",
  "/static/app.css?v=10",
  "/static/app.js?v=10",
  "/static/icon.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      caches.keys().then((names) =>
        Promise.all(
          names
            .filter((name) => name !== CACHE_NAME)
            .map((name) => caches.delete(name))
        )
      ),
      self.clients.claim()
    ])
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put("/", copy));
          return response;
        })
        .catch(() => caches.match("/"))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request))
  );
});

self.addEventListener("push", (event) => {
  let datos = {
    title: "ASTRO",
    body: "Tienes una nueva notificación.",
    url: "/",
    tag: "astro"
  };
  if (event.data) {
    try {
      datos = { ...datos, ...event.data.json() };
    } catch {
      datos.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(datos.title, {
      body: datos.body,
      icon: "/static/icon.svg",
      badge: "/static/icon.svg",
      tag: datos.tag,
      data: { url: datos.url }
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const destino = event.notification.data?.url || "/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((ventanas) => {
      for (const ventana of ventanas) {
        if ("focus" in ventana) {
          ventana.navigate(destino);
          return ventana.focus();
        }
      }
      return clients.openWindow(destino);
    })
  );
});
