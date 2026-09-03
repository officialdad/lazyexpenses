import { base } from '$app/paths';
import { SvelteMap } from 'svelte/reactivity';
import { toast } from './toast.svelte';
import { FRESH } from './fresh';

// Server-backed (cross-device) category confirmations (#82). Persisted in cats.json on
// the PVC, kept OUT of app.json (the pipeline regenerates app.json and would clobber it).
// Same shape as waivers.svelte.ts — same store, same optimistic-write-then-revert.
//
// The key is the merchant string app.json's `other[]` carries, which is
// insights.norm_merchant() output. parse.py normalises the same way before looking an
// override up, so a trailing reference token cannot split one merchant into two.
const GET = base + '/data/cats.json'; // served from the PVC in prod; static {} locally
const POST = base + '/api/cats';

const _map = new SvelteMap<string, string>();

export const cats = {
  /** Reactive merchant → category map. Absent = no confirmation, so CATS decides. */
  get map(): SvelteMap<string, string> {
    return _map;
  },

  /** The confirmed category for a merchant, or '' when nobody has said. */
  category(merchant: string): string {
    return _map.get(merchant) ?? '';
  },

  /** Hydrate from the server. Never throws; leaves the map empty on any failure. */
  async load(f: typeof fetch = fetch): Promise<void> {
    try {
      const res = await f(GET, FRESH);
      if (!res.ok) return;
      const obj = (await res.json()) as Record<string, string>;
      _map.clear();
      for (const [k, v] of Object.entries(obj)) _map.set(k, v);
    } catch {
      /* offline / no server — stay empty */
    }
  },

  /** Optimistically confirm (or, with '', clear) one merchant, then persist; revert if
   *  the write fails. true when it stuck. The server re-runs the pipeline before it
   *  answers, so the caller can reload app.json straight after this resolves. */
  async set(merchant: string, category: string, f: typeof fetch = fetch): Promise<boolean> {
    const prev = _map.get(merchant);
    if (category) _map.set(merchant, category);
    else _map.delete(merchant);
    try {
      const res = await f(POST, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ merchant, category: category || null })
      });
      if (!res.ok) throw new Error(`cats HTTP ${res.status}`);
      return true;
    } catch {
      toast('Couldn’t save — check your connection', 'error');
      if (prev === undefined) _map.delete(merchant);
      else _map.set(merchant, prev); // revert
      return false;
    }
  }
};
