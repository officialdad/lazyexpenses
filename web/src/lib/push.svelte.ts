// Web Push subscription (#39) — the default reminder transport, with no configuration.
//
// Every way this can fail is a sentence, not silence: push needs a secure context, iOS
// only allows it for an installed PWA, and the permission can be refused outright. The
// UI shows `note` whenever there is one, so the user learns why nothing happened.
import { toast } from './toast.svelte';

export type PushStatus = 'unknown' | 'unsupported' | 'off' | 'on' | 'denied' | 'busy';

export const push = $state<{ status: PushStatus; note: string }>({
	status: 'unknown',
	note: ''
});

const BLOCKED = 'Notifications are blocked for this site — turn them back on in your browser settings.';

/** iOS exposes PushManager only once the PWA is installed to the Home Screen. */
const isIOS = () =>
	typeof navigator !== 'undefined' && /iP(hone|ad|od)/.test(navigator.userAgent);

/** base64url VAPID key -> the Uint8Array PushManager.subscribe insists on. */
function keyBytes(b64: string): Uint8Array<ArrayBuffer> {
	const s = (b64 + '='.repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
	const bin = atob(s);
	// Built element by element rather than Uint8Array.from(): the latter is typed over
	// ArrayBufferLike, which BufferSource (what subscribe() wants) does not accept.
	const out = new Uint8Array(bin.length);
	for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
	return out;
}

const post = (body: unknown) => ({
	method: 'POST',
	headers: { 'content-type': 'application/json' },
	body: JSON.stringify(body)
});

/** Work out what this browser can do, and whether it is already subscribed. */
export async function initPush(): Promise<void> {
	if (typeof window === 'undefined') return;
	push.status = 'unsupported';
	if (!window.isSecureContext) {
		push.note = 'Reminders need HTTPS (or localhost) — this page is not on a secure connection.';
		return;
	}
	if (
		!('serviceWorker' in navigator) ||
		!('PushManager' in window) ||
		typeof Notification === 'undefined'
	) {
		push.note = isIOS()
			? 'On iPhone, add this app to your Home Screen first — Safari only allows reminders for an installed app.'
			: 'This browser cannot show push notifications.';
		return;
	}
	if (Notification.permission === 'denied') {
		push.status = 'denied';
		push.note = BLOCKED;
		return;
	}
	push.status = 'off';
	push.note = '';
	try {
		const reg = await navigator.serviceWorker.ready;
		if (await reg.pushManager.getSubscription()) push.status = 'on';
	} catch {
		/* no service worker yet — the button registers the subscription when asked */
	}
}

/** The on/off switch. Asks for permission only when the user actually asks for it. */
export async function togglePush(f: typeof fetch = fetch): Promise<void> {
	if (push.status !== 'on' && push.status !== 'off') return;
	const want = push.status === 'off';
	push.status = 'busy';
	try {
		const reg = await navigator.serviceWorker.ready;
		if (!want) {
			const sub = await reg.pushManager.getSubscription();
			// Tell the server first: if unsubscribe() succeeds and the POST does not, the
			// server would keep pushing to an endpoint the browser has already dropped.
			if (sub) {
				await f('/api/push/subscribe', post({ endpoint: sub.endpoint }));
				await sub.unsubscribe();
			}
			push.status = 'off';
			push.note = '';
			return;
		}
		if ((await Notification.requestPermission()) !== 'granted') {
			push.status = 'denied';
			push.note = BLOCKED;
			return;
		}
		const kr = await f('/api/push/key');
		if (!kr.ok) throw new Error(`key HTTP ${kr.status}`);
		const { key } = (await kr.json()) as { key: string };
		const sub = await reg.pushManager.subscribe({
			userVisibleOnly: true,
			applicationServerKey: keyBytes(key)
		});
		const saved = await f('/api/push/subscribe', post(sub.toJSON()));
		if (!saved.ok) throw new Error(`subscribe HTTP ${saved.status}`);
		push.status = 'on';
		push.note = '';
		toast('Reminders on — you will get a notification before each bill is due');
	} catch (e) {
		push.status = want ? 'off' : 'on';
		push.note = e instanceof Error ? e.message : String(e);
		toast('Couldn’t change reminders — check your connection', 'error');
	}
}
