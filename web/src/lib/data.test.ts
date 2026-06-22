import { describe, it, expect } from 'vitest';
import fixture from '../../static/data/app.json';
import { app, agg, meta, loadAppData } from './data';
import { monthlySeries, byCategory, topMerchants } from './trends';

const okFetch = (async () =>
  ({ ok: true, status: 200, json: async () => fixture })) as unknown as typeof fetch;
const failFetch = (async () =>
  ({ ok: false, status: 500, json: async () => ({}) })) as unknown as typeof fetch;

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
});
