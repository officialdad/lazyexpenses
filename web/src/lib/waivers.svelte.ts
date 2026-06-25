import { SvelteMap } from 'svelte/reactivity';
import { toast } from './toast.svelte';

// Server-backed (cross-device) waiver status. Persisted in waivers.json on the PVC,
// kept OUT of app.json (the pipeline regenerates app.json and would clobber it).
const GET = '/data/waivers.json'; // served from the PVC in prod; static {} locally
const POST = '/api/waivers';

export type WaiverStatus = 'tocall' | 'requested' | 'waived';
const ORDER: WaiverStatus[] = ['tocall', 'requested', 'waived'];
/** Cycle: To call → Requested → Waived → To call. */
export const nextStatus = (s: WaiverStatus): WaiverStatus => ORDER[(ORDER.indexOf(s) + 1) % ORDER.length];

const _map = new SvelteMap<string, WaiverStatus>();

export const waivers = {
  /** Reactive key → status map. 'tocall' is the implicit default (absent from the map). */
  get map(): SvelteMap<string, WaiverStatus> {
    return _map;
  },

  status(key: string): WaiverStatus {
    return _map.get(key) ?? 'tocall';
  },

  /** Hydrate from the server. Never throws; leaves the map empty on any failure. */
  async load(f: typeof fetch = fetch): Promise<void> {
    try {
      const res = await f(GET);
      if (!res.ok) return;
      const obj = (await res.json()) as Record<string, WaiverStatus>;
      _map.clear();
      for (const [k, v] of Object.entries(obj)) _map.set(k, v);
    } catch {
      /* offline / no server — stay empty */
    }
  },

  /** Optimistically set status, then persist; revert if the write fails.
   *  'tocall' (the default) is stored as a clear (status: null) to keep waivers.json small. */
  async set(key: string, status: WaiverStatus, f: typeof fetch = fetch): Promise<void> {
    const prev = _map.get(key);
    if (status === 'tocall') _map.delete(key);
    else _map.set(key, status);
    try {
      const res = await f(POST, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ key, status: status === 'tocall' ? null : status })
      });
      if (!res.ok) throw new Error(`waivers HTTP ${res.status}`);
    } catch {
      toast('Couldn’t save — check your connection', 'error');
      if (prev === undefined) _map.delete(key);
      else _map.set(key, prev); // revert
    }
  }
};
