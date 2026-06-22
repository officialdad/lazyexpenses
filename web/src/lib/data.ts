// Back-compat barrel. The runed store lives in data.svelte.ts; re-exporting the shared
// $state proxies here keeps every `import { app } from '$lib/data'` consumer reactive
// and unchanged (property mutation on a $state proxy propagates across the re-export).
export { app, meta, agg, latestMonth, loadAppData } from './data.svelte';
export type { LoadStatus } from './data.svelte';
