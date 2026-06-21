import { describe, it, expect } from 'vitest';
import { app, monthlyAll, byCategoryAll, topMerchantsAll } from './data';
import { monthlySeries, byCategory, topMerchants } from './trends';

describe('hoisted all-time aggregates', () => {
  it('monthlyAll equals monthlySeries over all rows', () => {
    expect(monthlyAll).toEqual(monthlySeries(app.rows, app.months, app.nonSpend));
  });
  it('byCategoryAll equals all-time byCategory', () => {
    expect(byCategoryAll).toEqual(byCategory(app.rows, null, app.nonSpend));
  });
  it('topMerchantsAll equals top 20 merchants', () => {
    expect(topMerchantsAll).toEqual(topMerchants(app.rows, 20, app.nonSpend));
  });
});
