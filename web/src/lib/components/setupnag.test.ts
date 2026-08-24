// #96: the setup nag, tested through both navs that render it.
//
// The one bug worth a test here is silent: `setupIncomplete` is a function (Svelte will
// not export a $derived from a module), so `{#if setupIncomplete}` is a truthy function
// object and rings the cog forever — including at someone whose setup is finished.
// Nothing else in the repo would catch that, so "configured => no ring" is the second case
// below and it runs against both navs.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/svelte';
import TopBar from './TopBar.svelte';
import BottomNav from './BottomNav.svelte';
import { cfg } from '$lib/setup.svelte';
import { nag, ensureSettings, markSetupSeen } from '$lib/setupnag.svelte';

const KEY = 'lazyexpenses:setup-seen';
// Both navs render the cog and both must behave the same, so the ring cases run over the
// pair. BottomNav takes no props, hence the cast to TopBar's signature.
const NAVS: [string, typeof TopBar][] = [
	['TopBar', TopBar],
	['BottomNav', BottomNav as typeof TopBar]
];

const ring = (c: HTMLElement) => c.querySelector('a[href="/settings"].nag');

beforeEach(() => {
	localStorage.clear();
	nag.seen = false;
	nag.pending = null;
	cfg.loaded = false;
	cfg.secrets = {};
	// Both navs call loadSettings() on mount. Stub fetch so no test touches the network,
	// and so the calls can be counted.
	vi.stubGlobal(
		'fetch',
		vi.fn(async () => new Response('{}', { headers: { 'content-type': 'application/json' } }))
	);
});
afterEach(() => vi.unstubAllGlobals());

const settingsCalls = () =>
	(fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls.filter((c) =>
		String(c[0]).endsWith('/api/settings')
	).length;

describe('setup nag', () => {
	it('rings the cog in both navs when nothing is configured', () => {
		cfg.loaded = true;
		for (const [name, C] of NAVS) {
			const { container } = render(C);
			const a = ring(container);
			expect(a, name).toBeTruthy();
			expect(a!.getAttribute('title'), name).toBe('Finish setup');
		}
	});

	// The `{#if setupIncomplete}` trap. A function object is truthy, so getting this wrong
	// pulses at a fully configured user and looks correct in every other test.
	it('does NOT ring when a mail password is configured', () => {
		cfg.loaded = true;
		cfg.secrets = { GMAIL_APP_PASSWORD: true };
		for (const [name, C] of NAVS) {
			const { container } = render(C);
			expect(ring(container), name).toBeNull();
		}
	});

	it('does NOT ring when only a bank PDF password is configured', () => {
		cfg.loaded = true;
		cfg.secrets = { CC_PW_MAYBANK: true };
		expect(ring(render(TopBar).container)).toBeNull();
	});

	// Before /api/settings answers there is nothing to be incomplete about, and a ring that
	// appears a beat after load is worse than one that never flickers.
	it('does NOT ring before settings have loaded', () => {
		expect(ring(render(TopBar).container)).toBeNull();
	});

	it('stops ringing once /settings has been reached, and remembers it', () => {
		cfg.loaded = true;
		markSetupSeen();
		for (const [name, C] of NAVS) {
			const { container } = render(C);
			expect(ring(container), name).toBeNull();
		}
		// The flag outlives the page, which is the whole point of putting it in storage.
		expect(localStorage.getItem(KEY)).toBe('1');
	});

	it('keeps the cog reachable and named while it rings', () => {
		cfg.loaded = true;
		const a = ring(render(TopBar).container)!;
		// #66's floor: an icon with no text still needs an accessible name.
		expect(a.getAttribute('aria-label')).toBe('Settings — finish setup');
		// The ring is a pseudo-element on the anchor, so nothing was added inside the icon.
		expect(a.querySelectorAll('svg').length).toBe(1);
	});

	it('asks the server once however many navs are mounted', async () => {
		render(TopBar);
		render(BottomNav);
		await ensureSettings();
		expect(settingsCalls()).toBe(1);
	});

	it('survives a private window, where touching localStorage throws', () => {
		const store = Object.getOwnPropertyDescriptor(window, 'localStorage')!;
		Object.defineProperty(window, 'localStorage', {
			configurable: true,
			get() {
				throw new DOMException('denied', 'SecurityError');
			}
		});
		try {
			cfg.loaded = true;
			expect(() => markSetupSeen()).not.toThrow();
			// The dismissal still holds for this page load; it just cannot outlive it.
			expect(ring(render(TopBar).container)).toBeNull();
		} finally {
			Object.defineProperty(window, 'localStorage', store);
		}
	});
});
