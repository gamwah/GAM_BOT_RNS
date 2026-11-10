// Offline support: the app and data are cached as you use them and served from
// cache when there is no connection.
const VERSION = "v1";
const SHELL = `rns-shell-${VERSION}`;
const DATA = `rns-data-${VERSION}`;
const SHELL_FILES = [
  "./", "index.html", "app.css", "app.js", "manifest.webmanifest",
  "icons/icon.svg", "icons/icon-192.png", "icons/favicon-32.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => ![SHELL, DATA].includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;  // never touch GitHub API calls

  // Network-first for everything: you always get the latest app and data when online,
  // and the last-seen copy when offline. (Cache-first would pin old app code until
  // someone remembered to bump VERSION.)
  const bucket = url.pathname.includes("/data/") ? DATA : SHELL;
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(bucket).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match("index.html")))
  );
});
