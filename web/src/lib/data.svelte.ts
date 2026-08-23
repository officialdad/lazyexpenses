import type { AppData } from './types';
import { monthlySeries, byCategory, topMerchants } from './trends';

export type LoadStatus = 'loading' | 'ready' | 'error' | 'auth' | 'setup';

const EMPTY: AppData = {
  rows: [], months: [], cards: [], cats: [], nonSpend: [],
  colors: {}, catIcon: {}, icons: {}, range: '',
  recs: [], installments: [], transfers: [],
  committed: { monthly: 0, subs: 0, installments: 0, subCats: [], items: [] },
  cycles: {}, bills: [], other: [], allCats: [],
};

// Live, reactive app data. Starts EMPTY (never rendered — +layout.svelte gates all
// consumers behind `meta.status === 'ready'`) and is filled IN PLACE after the runtime
// fetch, so every `import { app } from '$lib/data'` consumer keeps working unchanged.
export const app: AppData = $state({ ...EMPTY });

export const meta = $state<{ status: LoadStatus; error: string; lastSynced: number }>({
  status: 'loading',
  error: '',
  lastSynced: 0
});

// All-time aggregates, computed ONCE after fetch (the desktop+mobile dual subtree renders
// each chart twice but reads these same arrays — no recompute).
export const agg = $state<{
  monthly: ReturnType<typeof monthlySeries>;
  byCategory: ReturnType<typeof byCategory>;
  topMerchants: ReturnType<typeof topMerchants>;
}>({ monthly: [], byCategory: [], topMerchants: [] });

/** Latest statement month, or '' before data loads. A function (not a const) so it reflects
 *  the fetched data when a gated component instantiates. */
export function latestMonth(): string {
  return app.months[app.months.length - 1] ?? '';
}

/** Fetch /data/app.json at runtime, fill `app` in place, precompute aggregates.
 *  `f` is injectable for tests. Sets meta.status to ready|error; never throws. */
export async function loadAppData(f: typeof fetch = fetch): Promise<void> {
  meta.status = 'loading';
  meta.error = '';
  try {
    const res = await f('/data/app.json');
    // 401 = the server has APP_PASSWORD set and we have no session cookie. That is not
    // an error to retry, it is a prompt to show — a fourth state, not a fourth screen.
    if (res.status === 401) {
      meta.status = 'auth';
      return;
    }
    // 404 = an empty volume: nothing has been ingested yet. That is not a failure either,
    // it is the state first-run setup exists for (#40) — the old behaviour was a 404 and
    // a blank page, which told a new user nothing about what to do next.
    if (res.status === 404) {
      meta.status = 'setup';
      return;
    }
    if (!res.ok) throw new Error(`app.json HTTP ${res.status}`);
    const d = (await res.json()) as AppData;
    Object.assign(app, d);
    // ...and so is a volume whose pipeline ran over no statements at all.
    if (!app.rows.length) {
      meta.status = 'setup';
      return;
    }
    agg.monthly = monthlySeries(app.rows, app.months, app.nonSpend);
    agg.byCategory = byCategory(app.rows, null, app.nonSpend);
    agg.topMerchants = topMerchants(app.rows, 20, app.nonSpend);
    meta.lastSynced = Date.now();
    meta.status = 'ready';
  } catch (e) {
    meta.error = e instanceof Error ? e.message : String(e);
    meta.status = 'error';
  }
}

/** Exchange the shared password for a session cookie (HttpOnly — the browser holds it,
 *  this code never sees it). true on success. `f` injectable for tests; never throws. */
export async function login(password: string, f: typeof fetch = fetch): Promise<boolean> {
  try {
    const res = await f('/api/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ password })
    });
    return res.ok;
  } catch {
    return false;
  }
}
