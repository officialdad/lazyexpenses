import { SvelteSet } from 'svelte/reactivity';
import { toast } from './toast.svelte';

// Server-backed (cross-device) paid-bill state. Persisted in paid.json on the PVC,
// kept OUT of app.json (the pipeline regenerates app.json and would clobber it).
const GET = '/data/paid.json'; // served from the PVC in prod; static [] locally
const POST = '/api/paid';

const key = (bank: string, sm: string) => `${bank}|${sm}`;

const _keys = new SvelteSet<string>();

export const paid = {
  /** Reactive set of `bank|statement_month` keys — consumed by sortBills. */
  get keys(): SvelteSet<string> {
    return _keys;
  },

  has(bank: string, sm: string): boolean {
    return _keys.has(key(bank, sm));
  },

  /** Hydrate from the server. Never throws; leaves the set empty on any failure. */
  async load(f: typeof fetch = fetch): Promise<void> {
    try {
      const res = await f(GET);
      if (!res.ok) return;
      const arr = (await res.json()) as string[];
      _keys.clear();
      for (const k of arr) _keys.add(k);
    } catch {
      /* offline / no server — stay empty */
    }
  },

  /** Optimistically toggle, then persist; revert if the write fails. */
  async toggle(bank: string, sm: string, f: typeof fetch = fetch): Promise<void> {
    const k = key(bank, sm);
    const want = !_keys.has(k);
    if (want) _keys.add(k);
    else _keys.delete(k);
    try {
      const res = await f(POST, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ key: k, paid: want })
      });
      if (!res.ok) throw new Error(`paid HTTP ${res.status}`);
    } catch {
      toast('Couldn’t save — check your connection', 'error');
      if (want) _keys.delete(k);
      else _keys.add(k); // revert
    }
  }
};
