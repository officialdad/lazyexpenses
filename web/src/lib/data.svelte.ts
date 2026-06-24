import type { AppData } from './types';
import { monthlySeries, byCategory, topMerchants } from './trends';

export type LoadStatus = 'loading' | 'ready' | 'error';

const EMPTY: AppData = {
  rows: [], months: [], cards: [], cats: [], nonSpend: [],
  colors: {}, catIcon: {}, icons: {}, range: '',
  recs: [], installments: [], transfers: [],
  committed: { monthly: 0, subs: 0, installments: 0, subCats: [], items: [] },
  cycles: {}, bills: [],
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
    if (!res.ok) throw new Error(`app.json HTTP ${res.status}`);
    const d = (await res.json()) as AppData;
    Object.assign(app, d);
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
