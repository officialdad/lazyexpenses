// First-run setup and Settings (#40) — the browser half of /api/settings and /ingest.
//
// SECURITY: this module never holds a secret it did not just type. The server returns a
// configured/not-configured BOOLEAN per secret and never a value (server/settings.py), so
// there is nothing here to read back — a password field starts empty every time, and an
// empty field means "leave it alone", not "clear it". The case for putting a login in
// front of all this is filed as #65.

export type SettingsView = {
	/** Non-secret values, echoed back so a field can be pre-filled. */
	values: Record<string, string>;
	/** name -> is something set? NEVER the value. */
	secrets: Record<string, boolean>;
	/** Names the environment owns. Editing them cannot work, so the UI locks them. */
	locked: string[];
	/** The parser's bank keys, from parse.BANKS — the only valid `bank` for /ingest. */
	banks: string[];
	/** The gate is standing on `changeme@123`, the value .env.example publishes (#65). */
	default_password: boolean;
	/** No APP_PASSWORD at all, so there is no gate. Worse than the above, and it is the
	 *  state `default_password: false` cannot express — false there means "not the
	 *  published default", which is also true when there is no password (#72). */
	unauthenticated: boolean;
};

export type Ingested = {
	bank: string;
	recon: Record<string, number>;
	problems: Record<string, number>;
	warning: boolean;
	/** The uploaded PDF is encrypted and we have no password for that bank. */
	locked: boolean;
};

export const cfg = $state<SettingsView & { loaded: boolean }>({
	values: {},
	secrets: {},
	locked: [],
	banks: [],
	default_password: false,
	unauthenticated: false,
	loaded: false
});

export const isLocked = (name: string): boolean => cfg.locked.includes(name);

/** Human sentence for one reconciliation result. Pure — this is what the tests pin. */
export function reconLine(r: Ingested): string {
	if (r.locked) return `That ${r.bank.toUpperCase()} statement is password-protected.`;
	const n = (k: string) => r.recon[k] ?? 0;
	if (n('VERIFIED')) {
		const dup = n('DUPLICATE') ? `, ${n('DUPLICATE')} already had` : '';
		return `${n('VERIFIED')} statement(s) reconciled to the cent${dup}.`;
	}
	if (n('DUPLICATE')) return 'Already had that one — nothing changed.';
	const bad = Object.entries(r.problems)
		.map(([k, v]) => `${v} ${k}`)
		.join(', ');
	return bad ? `Could not read it: ${bad}.` : 'Nothing to reconcile in that file.';
}

async function detail(res: Response): Promise<string> {
	try {
		const b = (await res.json()) as { detail?: string };
		return b.detail || `HTTP ${res.status}`;
	} catch {
		return `HTTP ${res.status}`;
	}
}

const post = (body: unknown) => ({
	method: 'POST',
	headers: { 'content-type': 'application/json' },
	body: JSON.stringify(body)
});

function fill(d: SettingsView) {
	cfg.values = d.values ?? {};
	// Coerced, not copied: `secrets` is declared Record<string, boolean> and this is the
	// one line that makes that true. settings.public() already guarantees it server-side
	// and is tested there — this is so a value cannot reach the store even if that
	// invariant is ever broken upstream, because a bool here is what the UI renders.
	cfg.secrets = Object.fromEntries(Object.entries(d.secrets ?? {}).map(([k, v]) => [k, !!v]));
	cfg.locked = d.locked ?? [];
	cfg.banks = d.banks ?? [];
	// #74: these live on the store rather than in a second GET from the settings route,
	// because <Setup> needs them during first run too — and on an empty volume the
	// settings route is never mounted. Both default false: a fetch that failed must not
	// invent a security warning.
	cfg.default_password = !!d.default_password;
	cfg.unauthenticated = !!d.unauthenticated;
	cfg.loaded = true;
}

export async function loadSettings(f: typeof fetch = fetch): Promise<void> {
	try {
		const res = await f('/api/settings');
		if (res.ok) fill((await res.json()) as SettingsView);
	} catch {
		/* offline; the forms still render, saving will report the failure */
	}
}

/** Write a patch. "" clears a value; a key left out is untouched. '' on success,
 *  otherwise a sentence to show. Refreshes `cfg` from the response, so a saved secret
 *  flips to "configured" without anything ever coming back that could be read. */
export async function saveSettings(
	patch: Record<string, string>,
	f: typeof fetch = fetch
): Promise<string> {
	try {
		const res = await f('/api/settings', post(patch));
		if (!res.ok) return await detail(res);
		fill((await res.json()) as SettingsView);
		return '';
	} catch (e) {
		return e instanceof Error ? e.message : String(e);
	}
}

/** Test connection. Returns {ok, message} — a real result either way, which is the
 *  point: the alternative is silence and a mailbox that is never read. */
export async function testMail(f: typeof fetch = fetch): Promise<{ ok: boolean; message: string }> {
	try {
		const res = await f('/api/settings/test-mail', post({}));
		if (!res.ok) return { ok: false, message: await detail(res) };
		const d = (await res.json()) as { user: string; label: string; unread: number };
		return {
			ok: true,
			message: `Connected as ${d.user} — ${d.unread} unread in "${d.label}".`
		};
	} catch (e) {
		return { ok: false, message: e instanceof Error ? e.message : String(e) };
	}
}

export async function testReminder(
	f: typeof fetch = fetch
): Promise<{ ok: boolean; message: string }> {
	try {
		const res = await f('/api/settings/test-reminder', post({}));
		return res.ok
			? { ok: true, message: 'Sent — check your notifications.' }
			: { ok: false, message: await detail(res) };
	} catch (e) {
		return { ok: false, message: e instanceof Error ? e.message : String(e) };
	}
}

/** POST one statement to /ingest as multipart, exactly as fetch_mail.py does.
 *
 *  `bank` is permanent and load-bearing: it picks the PDF password, the parser branch and
 *  the stored filename, and parse.py re-derives the bank from that filename on every later
 *  run. An unknown value is a 400 (#31), but a wrong-but-valid one lands and misparses
 *  forever — which is why the UI makes the user choose and never guesses a default. */
export async function upload(
	bank: string,
	file: File,
	f: typeof fetch = fetch
): Promise<{ ok: boolean; result?: Ingested; error?: string }> {
	const body = new FormData();
	body.append('bank', bank);
	body.append('file', file);
	try {
		const res = await f('/ingest', { method: 'POST', body });
		if (!res.ok) return { ok: false, error: await detail(res) };
		return { ok: true, result: (await res.json()) as Ingested };
	} catch (e) {
		return { ok: false, error: e instanceof Error ? e.message : String(e) };
	}
}
