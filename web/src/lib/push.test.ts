// ?raw: Vite hands us the file as a string, so this needs no node types.
import pushSw from '../../static/push-sw.js?raw';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { push, initPush, togglePush } from './push.svelte';

// jsdom has no PushManager, so every branch is driven by faking the two globals push.ts
// actually reads: window.isSecureContext / PushManager, and navigator.serviceWorker.
const w = window as unknown as Record<string, unknown>;

function browser(opts: {
  secure?: boolean;
  pushManager?: boolean;
  permission?: NotificationPermission;
  subscribed?: boolean;
  ua?: string;
}) {
  const sub = {
    endpoint: 'https://push.example.net/abc',
    toJSON: () => ({ endpoint: 'https://push.example.net/abc', keys: { p256dh: 'B', auth: 'A' } }),
    unsubscribe: vi.fn(async () => true),
  };
  Object.defineProperty(window, 'isSecureContext', { value: opts.secure ?? true, configurable: true });
  if (opts.pushManager ?? true) w.PushManager = class {};
  else delete w.PushManager;
  w.Notification = {
    permission: opts.permission ?? 'default',
    requestPermission: vi.fn(async () => opts.permission ?? 'granted'),
  };
  Object.defineProperty(navigator, 'userAgent', { value: opts.ua ?? 'Chrome', configurable: true });
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: {
      ready: Promise.resolve({
        pushManager: {
          getSubscription: async () => (opts.subscribed ? sub : null),
          subscribe: vi.fn(async () => sub),
        },
      }),
    },
  });
  return sub;
}

beforeEach(() => {
  push.status = 'unknown';
  push.note = '';
});

describe('initPush', () => {
  it('says HTTPS is the problem instead of silently doing nothing', async () => {
    browser({ secure: false });
    await initPush();
    expect(push.status).toBe('unsupported');
    expect(push.note).toMatch(/HTTPS/);
  });

  it('tells an iPhone to install the app first', async () => {
    browser({ pushManager: false, ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)' });
    await initPush();
    expect(push.status).toBe('unsupported');
    expect(push.note).toMatch(/Home Screen/);
  });

  it('reports a blocked permission rather than prompting again', async () => {
    browser({ permission: 'denied' });
    await initPush();
    expect(push.status).toBe('denied');
    expect(push.note).toMatch(/blocked/i);
  });

  it('reads an existing subscription as already on', async () => {
    browser({ subscribed: true });
    await initPush();
    expect(push.status).toBe('on');
  });
});

describe('togglePush', () => {
  it('subscribes with the server key and POSTs the subscription', async () => {
    browser({ permission: 'granted' });
    await initPush();
    expect(push.status).toBe('off');
    const calls: [string, RequestInit | undefined][] = [];
    const f = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init]);
      return { ok: true, status: 200, json: async () => ({ key: 'BBBB' }) } as Response;
    }) as unknown as typeof fetch;
    await togglePush(f);
    expect(push.status).toBe('on');
    expect(calls[0][0]).toBe('/api/push/key');
    expect(calls[1][0]).toBe('/api/push/subscribe');
    expect(JSON.parse(calls[1][1]!.body as string).keys.p256dh).toBe('B');
  });

  it('turning it off tells the server before unsubscribing', async () => {
    const sub = browser({ permission: 'granted', subscribed: true });
    await initPush();
    expect(push.status).toBe('on');
    const order: string[] = [];
    const f = vi.fn(async (_u: string, init?: RequestInit) => {
      order.push('post:' + JSON.parse(init!.body as string).endpoint);
      return { ok: true, status: 200, json: async () => ({}) } as Response;
    }) as unknown as typeof fetch;
    sub.unsubscribe.mockImplementation(async () => {
      order.push('unsubscribe');
      return true;
    });
    await togglePush(f);
    expect(order).toEqual(['post:https://push.example.net/abc', 'unsubscribe']);
    expect(push.status).toBe('off');
  });

  it('a refused permission lands on denied, not a crash', async () => {
    browser({ permission: 'default' });
    await initPush();
    w.Notification = { permission: 'default', requestPermission: async () => 'denied' };
    await togglePush(vi.fn() as unknown as typeof fetch);
    expect(push.status).toBe('denied');
  });

  it('a failing server leaves the switch where it was', async () => {
    browser({ permission: 'granted' });
    await initPush();
    const f = vi.fn(async () => ({ ok: false, status: 503 }) as Response) as unknown as typeof fetch;
    await togglePush(f);
    expect(push.status).toBe('off');
    expect(push.note).toMatch(/503/);
  });
});

// static/push-sw.js is glue, but it is glue Workbox importScripts into a generated
// service worker where nothing else can see it. Evaluated here with a fake `self` so a
// change that breaks the payload contract with web_push.send() fails the suite.
describe('push-sw.js', () => {
  const load = () => {
    const listeners: Record<string, (e: unknown) => void> = {};
    const shown: [string, Record<string, unknown>][] = [];
    const sw = {
      addEventListener: (t: string, fn: (e: never) => void) => (listeners[t] = fn as (e: unknown) => void),
      registration: { showNotification: (t: string, o: Record<string, unknown>) => shown.push([t, o]) },
      clients: { matchAll: async () => [], openWindow: (u: string) => shown.push(['open', { u }]) },
    };
    new Function('self', pushSw)(sw);
    return { listeners, shown };
  };

  it('renders the {title, body, url} payload web_push.send() posts', () => {
    const { listeners, shown } = load();
    listeners.push({
      data: { json: () => ({ title: 'CIMB due', body: 'RM 1,234.50 by 2026-08-22', url: '/' }) },
      waitUntil: () => {},
    } as never);
    expect(shown[0][0]).toBe('CIMB due');
    expect(shown[0][1].body).toBe('RM 1,234.50 by 2026-08-22');
    expect((shown[0][1].data as { url: string }).url).toBe('/');
  });

  it('still shows something when the payload is not JSON', () => {
    const { listeners, shown } = load();
    listeners.push({
      data: {
        json: () => {
          throw new Error('nope');
        },
        text: () => 'plain',
      },
      waitUntil: () => {},
    } as never);
    expect(shown[0][0]).toBe('Bill due');
    expect(shown[0][1].body).toBe('plain');
  });
});
