import { describe, it, expect } from 'vitest';
import { cashbackFor, discretionaryTotal, prevMonth } from './spend';
import type { Row } from './types';
const NON = ['Installments/BT', 'Transfers/Payments', 'Rebate/Cashback'];
const r = (g: string, a: number, t: 0 | 1 = 0, m = '2026-06'): Row => ({ c: 'x', m, g, a, t, d: '' });

describe('spend helpers', () => {
  it('cashback sums credits in Rebate/Cashback', () => {
    expect(cashbackFor([r('Rebate/Cashback', 48, 1), r('F&B', 10)], '2026-06')).toBe(48);
  });
  it('discretionary total nets and excludes NON_SPEND', () => {
    expect(discretionaryTotal([r('F&B', 900), r('Installments/BT', 460), r('Travel', 100, 1)], '2026-06', NON)).toBe(800);
  });
  it('prevMonth returns the prior present month or null', () => {
    expect(prevMonth(['2026-04', '2026-05', '2026-06'], '2026-06')).toBe('2026-05');
    expect(prevMonth(['2026-06'], '2026-06')).toBe(null);
  });
});
