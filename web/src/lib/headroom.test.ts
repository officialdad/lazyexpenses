import { describe, it, expect } from 'vitest';
import { computeHeadroom } from './headroom';
import type { Row, Committed } from './types';

const NON = ['Installments/BT', 'Transfers/Payments', 'Rebate/Cashback'];
const committed = (monthly: number): Committed => ({ monthly, subs: 0, installments: monthly, items: [] });

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
});
