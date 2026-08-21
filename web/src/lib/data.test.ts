import { describe, it, expect } from 'vitest';
import fixture from '../../static/data/app.json';
import { app, agg, meta, loadAppData, login } from './data';
import { monthlySeries, byCategory, topMerchants } from './trends';

const okFetch = (async () =>
  ({ ok: true, status: 200, json: async () => fixture })) as unknown as typeof fetch;
const failFetch = (async () =>
  ({ ok: false, status: 500, json: async () => ({}) })) as unknown as typeof fetch;
const lockedFetch = (async () =>
  ({ ok: false, status: 401, json: async () => ({}) })) as unknown as typeof fetch;

describe('runtime data load', () => {
  it('marks status ready and fills app + aggregates once after fetch', async () => {
    await loadAppData(okFetch);
    expect(meta.status).toBe('ready');
    expect(app.rows.length).toBeGreaterThan(0);
    expect(agg.monthly).toEqual(monthlySeries(app.rows, app.months, app.nonSpend));
    expect(agg.byCategory).toEqual(byCategory(app.rows, null, app.nonSpend));
    expect(agg.topMerchants).toEqual(topMerchants(app.rows, 20, app.nonSpend));
  });

  it('sets error status + message on a non-ok response', async () => {
    await loadAppData(failFetch);
    expect(meta.status).toBe('error');
    expect(meta.error).toContain('500');
  });

  // #51: a 401 means the server has a password set, not that anything broke. The layout
  // renders a prompt for this state instead of "Couldn't load data" + a useless Retry.
  it('turns a 401 into the auth state, not an error', async () => {
    await loadAppData(lockedFetch);
    expect(meta.status).toBe('auth');
    expect(meta.error).toBe('');
  });
});

describe('login', () => {
  it('posts the password as json and reports success', async () => {
    let seen: [string, RequestInit] | null = null;
    const f = (async (url: string, init: RequestInit) => {
      seen = [url, init];
      return { ok: true, status: 200 };
    }) as unknown as typeof fetch;
    expect(await login('hunter2', f)).toBe(true);
    expect(seen![0]).toBe('/api/login');
    expect(JSON.parse(seen![1].body as string)).toEqual({ password: 'hunter2' });
  });

  it('reports failure on a rejected password and on a dead server', async () => {
    const no = (async () => ({ ok: false, status: 401 })) as unknown as typeof fetch;
    const dead = (async () => { throw new Error('offline'); }) as unknown as typeof fetch;
    expect(await login('wrong', no)).toBe(false);
    expect(await login('wrong', dead)).toBe(false);
  });
});
