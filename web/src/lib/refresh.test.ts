import { describe, it, expect } from 'vitest';
import { makeResumeRefresher, RESUME_FLOOR_MS } from './refresh';
import { FRESH } from './fresh';
import { loadAppData } from './data.svelte';
import { paid } from './paid.svelte';
import { cats } from './cats.svelte';
import { waivers } from './waivers.svelte';

describe('makeResumeRefresher', () => {
  it('does not fire inside the floor — onMount has just fetched', () => {
    let t = 1_000_000;
    let runs = 0;
    const r = makeResumeRefresher(() => runs++, () => t);
    r();                          // same instant as construction
    t += RESUME_FLOOR_MS - 1;
    r();
    expect(runs).toBe(0);
  });

  it('fires once past the floor, then re-arms', () => {
    let t = 1_000_000;
    let runs = 0;
    const r = makeResumeRefresher(() => runs++, () => t);
    t += RESUME_FLOOR_MS;
    r();
    expect(runs).toBe(1);
    r();                          // an immediate second resume is throttled
    expect(runs).toBe(1);
    t += RESUME_FLOOR_MS;
    r();
    expect(runs).toBe(2);
  });

  it('throttles a tab-switcher rather than hammering the server', () => {
    let t = 0;
    let runs = 0;
    const r = makeResumeRefresher(() => runs++, () => t);
    for (let i = 0; i < 100; i++) { t += 1000; r(); }   // 100 switches over 100s
    expect(runs).toBe(1);
  });
});

describe('/data/*.json are fetched with a revalidating cache mode', () => {
  // The prod bug: app.json is a FileResponse, so it carries Last-Modified. With no
  // Cache-Control beside it a browser computes heuristic freshness (~10% of
  // Date - Last-Modified) and answers from disk without contacting the origin — the
  // longer the file went unwritten, the longer the stale copy stayed pinned. The server
  // now sends `no-cache`; this is the client half, which is what covers a shell built
  // before that release.
  //
  // `no-cache`, NOT `no-store`: If-None-Match must still go out, so an unchanged 200KB
  // app.json comes back as a 304 with no body.
  it('sends cache: no-cache, not no-store', () => {
    expect(FRESH.cache).toBe('no-cache');
  });

  it('passes it on every one of the four loaders', async () => {
    const seen: RequestInit[] = [];
    const spy = ((_u: string, init?: RequestInit) => {
      seen.push(init ?? {});
      return Promise.resolve({
        ok: true, status: 200, json: () => Promise.resolve({})
      } as Response);
    }) as unknown as typeof fetch;

    await Promise.all([loadAppData(spy), paid.load(spy), cats.load(spy), waivers.load(spy)]);
    expect(seen).toHaveLength(4);
    for (const init of seen) expect(init.cache).toBe('no-cache');
  });
});
