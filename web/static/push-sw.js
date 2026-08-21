// Push handlers for the service worker (#39).
//
// Workbox `generateSW` writes sw.js and there is no way to add a listener to generated
// output, so vite.config.ts pulls this file in with workbox.importScripts. Do NOT move
// this into an injectManifest SW: the PWA wiring here is hand-held (see app.html) and
// swapping strategies breaks install + offline for a listener that importScripts adds
// in fifteen lines.
self.addEventListener('push', (event) => {
	let d = {};
	try {
		d = event.data ? event.data.json() : {};
	} catch {
		d = { body: event.data ? event.data.text() : '' };
	}
	event.waitUntil(
		self.registration.showNotification(d.title || 'Bill due', {
			body: d.body || '',
			icon: '/pwa-192x192.png',
			badge: '/pwa-192x192.png',
			// One notification per bill: a re-send replaces rather than stacks.
			tag: d.tag || d.title || 'bill',
			data: { url: d.url || '/' }
		})
	);
});

self.addEventListener('notificationclick', (event) => {
	event.notification.close();
	const url = (event.notification.data && event.notification.data.url) || '/';
	event.waitUntil(
		self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
			for (const w of wins) if ('focus' in w) return w.focus();
			return self.clients.openWindow(url);
		})
	);
});
