import { describe, it, expect } from 'vitest';
import { daysUntil, sortBills, URGENT_DAYS } from './bills';
import type { Bill } from './types';

const bill = (bank: string, due: string | null, bal: number | null = 100): Bill => ({
  bank,
  statement_month: '2026-06',
  current_balance: bal,
  payment_due_date: due,
  minimum_payment: null,
});

describe('daysUntil', () => {
  it('counts whole days from today to the due date', () => {
    expect(daysUntil('2026-06-25', '2026-06-22')).toBe(3);
    expect(daysUntil('2026-06-22', '2026-06-22')).toBe(0);
  });
  it('is negative when overdue and null when there is no due date', () => {
    expect(daysUntil('2026-06-20', '2026-06-22')).toBe(-2);
    expect(daysUntil(null, '2026-06-22')).toBe(null);
  });
  it('spans month boundaries correctly', () => {
    expect(daysUntil('2026-07-01', '2026-06-29')).toBe(2);
  });
});

describe('sortBills', () => {
  it('orders by due date ascending with null due dates last', () => {
    const bills = [bill('cimb', '2026-06-25'), bill('hsbc', null), bill('sc', '2026-06-23')];
    const out = sortBills(bills, '2026-06-22');
    expect(out.map((b) => b.bank)).toEqual(['sc', 'cimb', 'hsbc']);
    expect(out.map((b) => b.days)).toEqual([1, 3, null]);
  });
  it('flags urgent strictly under 3 days (and overdue), not at 3', () => {
    const bills = [bill('a', '2026-06-24'), bill('b', '2026-06-25'), bill('c', '2026-06-20')];
    const by = Object.fromEntries(sortBills(bills, '2026-06-22').map((b) => [b.bank, b.urgent]));
    expect(by['a']).toBe(true);   // 2 days -> urgent
    expect(by['b']).toBe(false);  // exactly 3 days -> not urgent
    expect(by['c']).toBe(true);   // overdue -> urgent
    expect(URGENT_DAYS).toBe(3);
  });
  it('never marks a null due date urgent', () => {
    const out = sortBills([bill('x', null)], '2026-06-22');
    expect(out[0].urgent).toBe(false);
  });
});
