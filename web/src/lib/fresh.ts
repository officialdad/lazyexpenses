// #118: fetch options for the four /data/*.json reads. The server is the real fix — those
// routes now send `Cache-Control: no-cache` — but this is what protects a client whose
// shell predates that release, and it costs nothing.
//
// Why this exists at all: app.json is served as a FileResponse, so it carries a
// Last-Modified. With no Cache-Control alongside it, a browser computes HEURISTIC
// freshness of ~10% of (Date - Last-Modified) and answers from disk without contacting
// the origin. The longer app.json went unwritten, the longer the stale copy stayed
// pinned — a newly ingested statement stayed invisible for hours.
//
// A hard reload does not clear that. The reload flag covers the document and the requests
// the page issues, but Workbox's NetworkFirst handler issues its OWN fetch inside the
// service worker, and that fetch does not inherit the flag.
//
// `no-cache`, NOT `no-store`. `no-store` would also defeat the stale copy but throws away
// the conditional GET: `no-cache` still sends If-None-Match, so an unchanged app.json
// comes back as a 304 with no body instead of re-downloading ~200KB on every load and
// every resume.
//
// This does not weaken offline. It sets the HTTP cache mode; the service worker's
// `app-data` Cache Storage entry is written by Workbox explicitly and is unaffected, so a
// failed network fetch still falls back to the last good copy.
export const FRESH: RequestInit = { cache: 'no-cache' };
