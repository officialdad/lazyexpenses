import fixture from '../static/data/app.json';
import { loadAppData } from './lib/data';

// jsdom has no IntersectionObserver, so any component using the `inview` action
// (MonthlyTrend, and anything else that lazy-reveals a chart) throws on mount.
// Stub fires immediately: these tests assert on rendered output, not on reveal timing.
class IO {
  constructor(private cb: IntersectionObserverCallback) {}
  observe(el: Element) {
    this.cb([{ isIntersecting: true, target: el } as IntersectionObserverEntry], this as never);
  }
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
}
globalThis.IntersectionObserver ??= IO as unknown as typeof IntersectionObserver;

// Populate the runed store once per test file so component tests that read `app`
// synchronously see real data (mirrors the old static-import behavior).
await loadAppData((async () =>
  ({ ok: true, status: 200, json: async () => fixture })) as unknown as typeof fetch);
