import { describe, it, expect } from 'vitest';
import { monthlySeries, byCategory, topMerchants } from './trends';
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
});
