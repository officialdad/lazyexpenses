import { describe, it, expect } from 'vitest';
import { monthlySeries, byCategory, topMerchants, monthDelta } from './trends';
import type { Row } from './types';
const NON = ['Installments/BT', 'Transfers/Payments', 'Rebate/Cashback'];
const r = (g: string, a: number, m: string, d = 'M', t: 0 | 1 = 0): Row => ({ c: 'x', m, g, a, t, d });

describe('trends aggregation', () => {
  it('monthlySeries totals discretionary per month in order', () => {
    const rows = [r('F&B', 100, '2026-05'), r('F&B', 200, '2026-06'), r('Installments/BT', 999, '2026-06')];
    expect(monthlySeries(rows, ['2026-05', '2026-06'], NON)).toEqual([
      { month: '2026-05', total: 100 }, { month: '2026-06', total: 200 }
    ]);
  });
  it('byCategory sorts desc and skips NON_SPEND', () => {
    const rows = [r('F&B', 100, '2026-06'), r('Travel', 300, '2026-06'), r('Rebate/Cashback', 50, '2026-06', 'cb', 1)];
    expect(byCategory(rows, '2026-06', NON)).toEqual([
      { g: 'Travel', total: 300 }, { g: 'F&B', total: 100 }
    ]);
  });
  it('topMerchants returns the n biggest by netted spend', () => {
    const rows = [r('F&B', 100, '2026-06', 'A'), r('F&B', 250, '2026-06', 'B')];
    expect(topMerchants(rows, 1, NON)).toEqual([{ d: 'B', total: 250 }]);
  });

  it('monthDelta gives signed Δ vs prior month, null for first/unknown', () => {
    const s = [{ month: '2026-05', total: 100 }, { month: '2026-06', total: 130 }, { month: '2026-07', total: 90 }];
    expect(monthDelta(s, '2026-06')).toEqual({ abs: 30, pct: 0.3 });   // up
    expect(monthDelta(s, '2026-07')).toEqual({ abs: -40, pct: -40 / 130 }); // down
    expect(monthDelta(s, '2026-05')).toBeNull(); // first
    expect(monthDelta(s, '2026-09')).toBeNull(); // unknown
  });

  it('month-filtered topMerchants excludes other months', () => {
    const rows = [r('F&B', 500, '2026-05', 'Old'), r('F&B', 80, '2026-06', 'New')];
    const m = '2026-06';
    expect(topMerchants(rows.filter((x) => x.m === m), 5, NON)).toEqual([{ d: 'New', total: 80 }]);
  });
});
