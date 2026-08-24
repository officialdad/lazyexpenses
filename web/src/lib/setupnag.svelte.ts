// #96: the Settings cog nags until setup is finished.
//
// A dashboard with data but no mailbox wired reads exactly like a broken one — #92's
// reporter got an empty screen and no reason for it. This is the visible pointer at the
// one screen that fixes it.
//
// It lives here rather than in either nav because BOTH navs are mounted at every width:
// +layout toggles them with display:none (lg:hidden / hidden lg:block), which hides a
// subtree without unmounting it. A copy per component would be two GETs of /api/settings
// and two dismissal flags that could disagree.
import { loadSettings, setupIncomplete } from '$lib/setup.svelte';

const KEY = 'lazyexpenses:setup-seen';

// A private window throws on the property access itself, not only on the call, so every
// touch of localStorage is wrapped. Failing closed (false) is the right default: the nag
// then survives until the config is actually finished, which is the honest signal.
function read(): boolean {
	try {
		return localStorage.getItem(KEY) === '1';
	} catch {
		return false;
	}
}

/** One mutable state object, the same shape `search.svelte.ts` uses — a plain `let $state`
 *  cannot be reset by a test, and re-importing the module to get a fresh one hands the
 *  component a second Svelte runtime (`effect_orphan`).
 *
 *  - `seen`: /settings has been reached, this load or an earlier one.
 *  - `pending`: the in-flight GET, so the second nav to mount joins it instead of firing
 *    its own. Both navs are mounted at every width, so this is not hypothetical. */
export const nag = $state<{ seen: boolean; pending: Promise<void> | null }>({
	seen: read(),
	pending: null
});

/** The one GET. Both navs call this on mount; the second caller gets the first's promise. */
export function ensureSettings(): Promise<void> {
	return (nag.pending ??= loadSettings());
}

/** /settings has been reached. Dismisses the nag permanently, even if nothing was saved —
 *  once the user has seen that screen, pulsing at them is nagging about a decision they
 *  have already made. */
export function markSetupSeen(): void {
	nag.seen = true;
	try {
		localStorage.setItem(KEY, '1');
	} catch {
		/* private window: the nag comes back next load, which is the safe way to be wrong */
	}
}

/** Ring the cog?
 *
 *  CALL IT — `nagSetup()`, never `{#if nagSetup}`. `setupIncomplete` is a function because
 *  Svelte refuses to export `$derived` from a module (`derived_invalid_export`), and a bare
 *  function object is always truthy: the mistake pulses the cog forever, at a fully
 *  configured user, in silence. `setupnag.test.ts` renders a configured cfg and asserts no
 *  ring for exactly that reason. `cfg` is `$state`, so this tracks like a derived. */
export function nagSetup(): boolean {
	return !nag.seen && setupIncomplete();
}
