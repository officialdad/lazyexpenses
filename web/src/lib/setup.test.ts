import { describe, it, expect } from 'vitest';
import {
	cfg,
	isLocked,
	loadSettings,
	saveSettings,
	testMail,
	testReminder,
	upload,
	reconLine,
	backfillLine,
	setupIncomplete,
	startBackfill,
	backfillStatus,
	type Backfill,
	type Ingested
} from './setup.svelte';

const json = (body: unknown, status = 200) =>
	(async () => ({ ok: status < 400, status, json: async () => body, text: async () => '' })) as unknown as typeof fetch;

const VIEW = {
	values: { GMAIL_USER: 'me@example.com', GMAIL_LABEL: 'CC' },
	secrets: { GMAIL_APP_PASSWORD: true, TELEGRAM_BOT_TOKEN: false, CC_PW_CIMB: false },
	locked: ['GMAIL_USER'],
	banks: ['maybank', 'cimb', 'sc', 'alliance', 'hsbc', 'rhb']
};

const ing = (over: Partial<Ingested> = {}): Ingested => ({
	bank: 'cimb',
	recon: {},
	problems: {},
	warning: false,
	locked: false,
	...over
});

describe('settings view', () => {
	it('carries the two gate flags, defaulting both to false when the fetch says nothing', async () => {
		// #74: they live on the shared store so <Setup> can read them during first run,
		// when the /settings route is not mounted. Defaulting false is deliberate — a
		// server that answered nothing must not invent a security warning.
		await loadSettings(json({ ...VIEW, unauthenticated: true }));
		expect(cfg.unauthenticated).toBe(true);
		expect(cfg.default_password).toBe(false);
		await loadSettings(json(VIEW));
		expect(cfg.unauthenticated).toBe(false);
		expect(cfg.default_password).toBe(false);
	});

	it('fills the store and reports env-owned names as locked', async () => {
		await loadSettings(json(VIEW));
		expect(cfg.loaded).toBe(true);
		expect(cfg.banks).toHaveLength(6);
		expect(cfg.values.GMAIL_USER).toBe('me@example.com');
		expect(isLocked('GMAIL_USER')).toBe(true);
		expect(isLocked('GMAIL_LABEL')).toBe(false);
	});

	// SECURITY (#40): the server only ever sends a bool per secret. Nothing in this module
	// may turn that into a value, and nothing may keep one around after it is posted.
	it('holds no secret value anywhere — only configured booleans', async () => {
		// A server that wrongly echoed the value would send it in exactly this shape.
		await loadSettings(
			json({ ...VIEW, secrets: { ...VIEW.secrets, GMAIL_APP_PASSWORD: 'hunter2-abcd' } })
		);
		expect(typeof cfg.secrets.GMAIL_APP_PASSWORD).toBe('boolean');
		expect(cfg.secrets.GMAIL_APP_PASSWORD).toBe(true);

		// Scans VALUES, not the serialized store: `default_password` is a bool whose NAME
		// contains "password" (#74), and matching on that is a false positive, not a leak.
		const strings = (v: unknown): string[] =>
			typeof v === 'string' ? [v] : v && typeof v === 'object' ? Object.values(v).flatMap(strings) : [];
		for (const s of strings(cfg)) expect(s.toLowerCase()).not.toContain('hunter2');
	});

	it('posts a patch and refreshes from the response', async () => {
		let seen: [string, RequestInit] | null = null;
		const f = (async (url: string, init: RequestInit) => {
			seen = [url, init];
			return { ok: true, status: 200, json: async () => ({ ...VIEW, locked: [] }) };
		}) as unknown as typeof fetch;
		expect(await saveSettings({ GMAIL_LABEL: 'Statements' }, f)).toBe('');
		expect(seen![0]).toBe('/api/settings');
		expect(JSON.parse(seen![1].body as string)).toEqual({ GMAIL_LABEL: 'Statements' });
		expect(isLocked('GMAIL_USER')).toBe(false);
	});

	it('returns the server sentence on a rejected write instead of throwing', async () => {
		expect(await saveSettings({ PATH: 'x' }, json({ detail: 'unknown setting(s): PATH' }, 400)))
			.toBe('unknown setting(s): PATH');
		const dead = (async () => {
			throw new Error('offline');
		}) as unknown as typeof fetch;
		expect(await saveSettings({ GMAIL_LABEL: 'x' }, dead)).toBe('offline');
	});
});

describe('test buttons', () => {
	it('reports what the mailbox actually contained', async () => {
		const r = await testMail(json({ ok: true, user: 'me@example.com', label: 'CC', unread: 2 }));
		expect(r).toEqual({ ok: true, message: 'Connected as me@example.com — 2 unread in "CC".' });
	});

	it('reports a real failure, not silence', async () => {
		const r = await testMail(json({ detail: 'AUTHENTICATIONFAILED' }, 400));
		expect(r).toEqual({ ok: false, message: 'AUTHENTICATIONFAILED' });
		const t = await testReminder(json({ detail: 'no reminder transport configured' }, 400));
		expect(t.ok).toBe(false);
		expect(t.message).toContain('no reminder transport');
	});

	it('confirms a sent test reminder', async () => {
		expect((await testReminder(json({ ok: true }))).ok).toBe(true);
	});
});

describe('upload', () => {
	it('posts the chosen bank and the file as multipart', async () => {
		let seen: [string, RequestInit] | null = null;
		const f = (async (url: string, init: RequestInit) => {
			seen = [url, init];
			return { ok: true, status: 200, json: async () => ing({ recon: { VERIFIED: 1 } }) };
		}) as unknown as typeof fetch;
		const file = new File([new Uint8Array([1, 2, 3])], 'x.pdf', { type: 'application/pdf' });
		const res = await upload('cimb', file, f);
		expect(res.ok).toBe(true);
		expect(seen![0]).toBe('/ingest');
		const body = seen![1].body as FormData;
		// `bank` is permanent — it must be exactly what the user picked, never inferred
		// from the filename (parse.py re-derives the bank from it forever after).
		expect(body.get('bank')).toBe('cimb');
		expect((body.get('file') as File).name).toBe('x.pdf');
	});

	it('surfaces the server 400 for an unknown bank (#31)', async () => {
		const res = await upload('mybank', new File([''], 'x.pdf'),
			json({ detail: "unknown bank 'mybank'; expected one of: maybank, cimb" }, 400));
		expect(res.ok).toBe(false);
		expect(res.error).toContain('unknown bank');
	});
});

describe('reconLine', () => {
	it('says what happened in each outcome', () => {
		expect(reconLine(ing({ recon: { VERIFIED: 1 } }))).toBe(
			'1 statement(s) reconciled to the cent.'
		);
		expect(reconLine(ing({ recon: { VERIFIED: 2, DUPLICATE: 1 } }))).toBe(
			'2 statement(s) reconciled to the cent, 1 already had.'
		);
		expect(reconLine(ing({ recon: { DUPLICATE: 1 } }))).toBe(
			'Already had that one — nothing changed.'
		);
		expect(reconLine(ing({ recon: { REVIEW: 1 }, problems: { REVIEW: 1 }, warning: true })))
			.toBe('Could not read it: 1 REVIEW.');
	});

	it('names the bank when the PDF is locked, because that is the question to ask', () => {
		expect(reconLine(ing({ bank: 'cimb', recon: { ERROR: 1 }, problems: { ERROR: 1 }, locked: true })))
			.toBe('That CIMB statement is password-protected.');
	});
});

const bf = (over: Partial<Backfill> = {}): Backfill => ({
	running: false,
	total: 0,
	done: 0,
	ingested: 0,
	skipped: 0,
	failed: 0,
	unknown: [],
	locked: [],
	error: null,
	...over
});

describe('backfill (#91)', () => {
	it('reports progress while it runs and the tally when it stops', () => {
		expect(backfillLine(bf({ running: true, total: 120, done: 7, ingested: 5 }))).toBe(
			'Reading mail… 7 of 120, 5 imported.'
		);
		expect(backfillLine(bf({ total: 120, done: 120, ingested: 84, skipped: 36 }))).toBe(
			'Read 120 mail: 84 imported, 36 skipped.'
		);
		expect(backfillLine(bf({ total: 3, done: 3, ingested: 2, skipped: 1, failed: 1 }))).toBe(
			'Read 3 mail: 2 imported, 1 skipped. 1 failed — see the server log.'
		);
		expect(backfillLine(bf())).toBe('Nothing in that label to import.');
	});

	it('says an unrecognised bank was skipped — a backfill has no unread pile to nag from', () => {
		expect(
			backfillLine(bf({ total: 2, done: 2, ingested: 1, skipped: 1, unknown: ['Your statement'] }))
		).toContain('1 had no recognisable bank');
	});

	// #95: the beginner path imported 15 statements that all failed to decrypt and read as
	// success. A failure now names the cause whenever the server counted it.
	it('blames the missing password when the server named the locked banks', () => {
		expect(
			backfillLine(bf({ total: 15, done: 15, ingested: 0, skipped: 0, failed: 15, locked: ['cimb'] }))
		).toBe(
			'Read 15 mail: 0 imported, 0 skipped. 15 failed — the CIMB statements are password-protected. Add the password in step 2.'
		);
		expect(
			backfillLine(bf({ total: 4, done: 4, ingested: 2, skipped: 0, failed: 2, locked: ['cimb', 'rhb'] }))
		).toContain('the CIMB, RHB statements are password-protected');
		// The Python half lands separately, so `locked` is empty until then — an empty
		// list must not invent a cause.
		expect(backfillLine(bf({ total: 1, done: 1, failed: 1 }))).toContain('see the server log');
	});

	it('fills in `locked` when the server has not started sending it yet', async () => {
		const b = await backfillStatus(json({ running: false, total: 0, done: 0, ingested: 0, skipped: 0, failed: 0, unknown: [], error: null }));
		expect(b!.locked).toEqual([]);
	});

	it('shows the server error rather than a stuck progress line', () => {
		expect(backfillLine(bf({ error: 'AUTHENTICATIONFAILED' }))).toBe(
			'Import failed: AUTHENTICATIONFAILED'
		);
	});

	it('surfaces the 409 when one is already running', async () => {
		const res = await startBackfill(json({ detail: 'A backfill is already running.' }, 409));
		expect(res).toEqual({ ok: false, message: 'A backfill is already running.' });
	});

	it('returns null for a dropped poll instead of inventing a state', async () => {
		expect(await backfillStatus(json({}, 500))).toBeNull();
		const offline = (async () => {
			throw new Error('offline');
		}) as unknown as typeof fetch;
		expect(await backfillStatus(offline)).toBeNull();
	});
});

// #95: the nav pulses the Settings cog while this is true, so the predicate lives here —
// the wave-2 issue owns only the nav components.
describe('setupIncomplete', () => {
	it('is true on a virgin config and false once any password exists', async () => {
		await loadSettings(
			json({ ...VIEW, secrets: { GMAIL_APP_PASSWORD: false, CC_PW_CIMB: false } })
		);
		expect(setupIncomplete()).toBe(true);

		await loadSettings(json({ ...VIEW, secrets: { GMAIL_APP_PASSWORD: true, CC_PW_CIMB: false } }));
		expect(setupIncomplete()).toBe(false);

		await loadSettings(json({ ...VIEW, secrets: { GMAIL_APP_PASSWORD: false, CC_PW_CIMB: true } }));
		expect(setupIncomplete()).toBe(false);
	});

	it('stays false before the server has answered — an unloaded store is not a verdict', () => {
		cfg.loaded = false;
		cfg.secrets = {};
		expect(setupIncomplete()).toBe(false);
		cfg.loaded = true;
		expect(setupIncomplete()).toBe(true);
	});
});
