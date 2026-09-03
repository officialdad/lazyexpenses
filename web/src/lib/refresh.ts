import { loadAppData } from './data.svelte';
import { paid } from './paid.svelte';
import { waivers } from './waivers.svelte';
import { cats } from './cats.svelte';

/** Re-read all four server-backed sources — the same list `+layout.svelte` loads on
 *  mount, kept here so the two cannot drift. Every loader swallows its own errors, so
 *  this never throws and a dead network leaves the last good data on screen. */
export async function refreshAll(): Promise<void> {
  await Promise.all([loadAppData(), paid.load(), waivers.load(), cats.load()]);
}

/** The same 60s floor `app.html` uses for its `reg.update()` check, for the same reason:
 *  a tab-switcher must not be able to hammer the server. */
export const RESUME_FLOOR_MS = 60_000;

/** Build the `visibilitychange` handler.
 *
 *  #118. `app.html` already polls for a new SHELL on resume (#67). Data had none: it
 *  loaded once in onMount and never again, so an installed PWA resumed from the
 *  background could render days-old bills with nothing on screen looking wrong. That is
 *  the half of staleness a Cache-Control header cannot fix — the client was not asking
 *  at all.
 *
 *  `last` is seeded to now, not 0: onMount has just fetched, so a tab-out-and-back inside
 *  the first minute has nothing to collect.
 *
 *  Args are injected for tests. */
export function makeResumeRefresher(
  run: () => void = () => void refreshAll(),
  now: () => number = Date.now,
  floorMs: number = RESUME_FLOOR_MS
): () => void {
  let last = now();
  return () => {
    if (now() - last < floorMs) return;
    last = now();
    run();
  };
}
