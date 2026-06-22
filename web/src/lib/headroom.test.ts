import { describe, it, expect } from 'vitest';
import { computeHeadroom } from './headroom';
import type { Row, Committed } from './types';

const round2 = (n: number) => Math.round(n * 100) / 100;
const NON = ['Installments/BT', 'Transfers/Payments', 'Rebate/Cashback'];
const committed = (monthly: number): Committed => ({ monthly, subs: 0, installments: monthly, subCats: ['Subscriptions'], items: [] });

const r = (g: string, a: number, t: 0 | 1 = 0): Row => ({ c: 'x', m: '2026-06', g, a, t, d: '' });

describe('computeHeadroom', () => {
  it('splits ceiling into locked/spent/free', () => {
    const rows = [r('F&B', 900), r('Groceries', 600)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committed(640), nonSpend: NON });
    expect(h.locked).toBe(640);
    expect(h.spent).toBe(1500);
    expect(h.free).toBe(860);
    expect(h.status).toBe('ok');
  });

  it('excludes Subscriptions from spent (no double-count with locked)', () => {
    const rows = [r('F&B', 900), r('Subscriptions', 85)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committed(640), nonSpend: NON });
    expect(h.spent).toBe(900);                       // 85 sub charge NOT counted
  });

  it('excludes NON_SPEND categories from spent', () => {
    const rows = [r('F&B', 900), r('Installments/BT', 460), r('Transfers/Payments', 2000)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committed(640), nonSpend: NON });
    expect(h.spent).toBe(900);
  });

  it('nets refunds (credit) within a consumption category', () => {
    const rows = [r('Travel', 1000), r('Travel', 300, 1)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committed(0), nonSpend: NON });
    expect(h.spent).toBe(700);
  });

  it('status over when used exceeds ceiling', () => {
    const rows = [r('F&B', 1500)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 2000, committed: committed(640), nonSpend: NON });
    expect(h.free).toBe(-140);
    expect(h.status).toBe('over');
  });

  it('status over when commitments alone exceed ceiling', () => {
    const h = computeHeadroom({ rows: [], month: '2026-06', ceiling: 500, committed: committed(640), nonSpend: NON });
    expect(h.free).toBe(-140);
    expect(h.status).toBe('over');
  });

  it('status warn when free is below 10% of ceiling', () => {
    const rows = [r('F&B', 2200)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committed(640), nonSpend: NON });
    expect(h.free).toBe(160);
    expect(h.status).toBe('warn');
  });

  it('only counts rows in the target month (month filter)', () => {
    const may: Row = { c: 'x', m: '2026-05', g: 'F&B', a: 5000, t: 0, d: '' };
    const jul: Row = { c: 'x', m: '2026-07', g: 'F&B', a: 4000, t: 0, d: '' };
    const rows = [r('F&B', 900), may, jul];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committed(0), nonSpend: NON });
    expect(h.spent).toBe(900);                       // May + Jul charges excluded
  });

  it('status ok at exactly the warn boundary (free === 10% of ceiling)', () => {
    const rows = [r('F&B', 2700)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committed(0), nonSpend: NON });
    expect(h.free).toBe(300);                         // 10% of 3000
    expect(h.status).toBe('ok');                      // strict `<` → boundary is ok, not warn
  });

  it('status warn just below the warn boundary', () => {
    const rows = [r('F&B', 2701)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committed(0), nonSpend: NON });
    expect(h.free).toBe(299);
    expect(h.status).toBe('warn');
  });

  it('status warn (not over) when used exactly equals ceiling', () => {
    const rows = [r('F&B', 3000)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committed(0), nonSpend: NON });
    expect(h.free).toBe(0);
    expect(h.status).toBe('warn');                    // `over` needs used > ceiling (strict)
  });

  it('excludes Telco/Utilities from spent when subCats includes it (no double-count)', () => {
    // Telco sub (e.g. TIMEDOTCOM ~RM208.82) is in committed.subs AND appears as a row.
    // subCats: ['Telco/Utilities'] → skip set must exclude it from spent.
    const telcoMonthly = 208.82;
    const committedWithTelco: Committed = {
      monthly: telcoMonthly,
      subs: telcoMonthly,
      installments: 0,
      subCats: ['Telco/Utilities'],
      items: [{ name: 'TIMEDOTCOM SHAH ALAM', monthly: telcoMonthly, kind: 'sub' }],
    };
    const rows = [r('F&B', 900), r('Telco/Utilities', telcoMonthly)];
    const h = computeHeadroom({ rows, month: '2026-06', ceiling: 3000, committed: committedWithTelco, nonSpend: NON });
    // Telco charge must NOT appear in spent — it's already in locked
    expect(h.spent).toBe(900);
    expect(h.locked).toBe(telcoMonthly);
    expect(h.used).toBe(round2(telcoMonthly + 900));
    expect(h.free).toBe(round2(3000 - telcoMonthly - 900));
  });
});
