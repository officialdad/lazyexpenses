// Online/offline awareness for stale-data cues. Wired once from +layout onMount.
export const net = $state({ online: true });

// ponytail: no teardown — +layout is the app root and never unmounts, so the
// listeners live for the page lifetime. Add cleanup if this ever moves.
export function initNet(): void {
  if (typeof navigator === 'undefined' || typeof window === 'undefined') return;
  net.online = navigator.onLine;
  window.addEventListener('online', () => (net.online = true));
  window.addEventListener('offline', () => (net.online = false));
}
