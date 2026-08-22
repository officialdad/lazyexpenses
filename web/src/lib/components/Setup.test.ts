import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, waitFor } from '@testing-library/svelte';
import Setup from './Setup.svelte';
import { cfg } from '$lib/setup.svelte';

const VIEW = {
	values: { GMAIL_USER: '', GMAIL_LABEL: '' },
	secrets: { GMAIL_APP_PASSWORD: false, TELEGRAM_BOT_TOKEN: false },
	locked: [] as string[],
	banks: ['maybank', 'cimb', 'sc', 'alliance', 'hsbc', 'rhb']
};

function stubFetch(view = VIEW) {
	vi.stubGlobal(
		'fetch',
		vi.fn(async () => ({ ok: true, status: 200, json: async () => view }))
	);
}

describe('Setup', () => {
	beforeEach(() => {
		cfg.locked = [];
		stubFetch();
	});

	it('leads with the upload step and lists every bank the parser dispatches', async () => {
		const { container, getByText } = render(Setup, { props: { first: true } });
		expect(getByText('1 · Add a statement')).toBeTruthy();
		await waitFor(() => expect(container.querySelectorAll('#setup-bank option').length).toBe(7));
		const select = container.querySelector('#setup-bank') as HTMLSelectElement;
		// no default, ever: `bank` is permanent and a wrong-but-valid guess misparses
		// that statement forever (#31). The user has to choose.
		expect(select.value).toBe('');
		expect(select.querySelector('option[value=""]')?.hasAttribute('disabled')).toBe(true);
		expect([...select.options].map((o) => o.value).slice(1)).toEqual(VIEW.banks);
		// ...and nothing can be posted until they have
		expect((container.querySelector('button[type="submit"]') as HTMLButtonElement).disabled).toBe(
			true
		);
	});

	it('does not ask for statement passwords unprompted on a first run', async () => {
		const { queryByText } = render(Setup, { props: { first: true } });
		await waitFor(() => expect(cfg.banks.length).toBe(6));
		// step 2 is asked in context, when a real file came back locked — a cold grid of
		// six password boxes is the terminal experience #40 exists to delete
		expect(queryByText('2 · Statement passwords')).toBeNull();
	});

	it('offers all four steps when revisited as Settings', async () => {
		const { getByText } = render(Setup, { props: { first: false } });
		await waitFor(() => expect(cfg.banks.length).toBe(6));
		expect(getByText('Settings')).toBeTruthy();
		expect(getByText('2 · Statement passwords')).toBeTruthy();
		for (const id of ['pw-maybank', 'pw-cimb', 'pw-rhb'])
			expect(document.getElementById(id)).toBeTruthy();
	});

	it('locks a field the environment owns instead of pretending an edit would work', async () => {
		stubFetch({ ...VIEW, locked: ['GMAIL_USER', 'CC_PW_CIMB'] });
		const { container, getAllByText } = render(Setup, { props: { first: false } });
		await waitFor(() => expect(cfg.locked.length).toBe(2));
		expect((container.querySelector('#gmail-user') as HTMLInputElement).disabled).toBe(true);
		expect((container.querySelector('#pw-cimb') as HTMLInputElement).disabled).toBe(true);
		expect((container.querySelector('#pw-hsbc') as HTMLInputElement).disabled).toBe(false);
		expect(getAllByText('Locked — set by the environment').length).toBe(2);
	});

	it('never prefills a secret — a password box starts empty however configured it is', async () => {
		stubFetch({ ...VIEW, secrets: { GMAIL_APP_PASSWORD: true, TELEGRAM_BOT_TOKEN: true } });
		const { container } = render(Setup, { props: { first: false } });
		await waitFor(() => expect(cfg.secrets.GMAIL_APP_PASSWORD).toBe(true));
		for (const id of ['#gmail-pw', '#tg-token']) {
			const el = container.querySelector(id) as HTMLInputElement;
			expect(el.value).toBe('');
			expect(el.type).toBe('password');
			// the only hint it may carry is that something is already stored
			expect(el.placeholder).toBe('unchanged');
		}
	});
});
