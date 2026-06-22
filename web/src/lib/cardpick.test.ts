import { describe, it, expect } from 'vitest';
import { rankCards, runwayDays, prettyCard, todayMYT } from './cardpick';
import type { Row } from './types';

const NON = ['Installments/BT', 'Transfers/Payments', 'Rebate/Cashback'];
const r = (c: string, g: string, a: number, t: 0 | 1 = 0, m = '2026-06'): Row => ({ c, m, g, a, t, d: '' });

describe('runwayDays', () => {
  it('counts days to the next occurrence of the cycle day, strictly after today', () => {
    expect(runwayDays('2026-06-10', 16)).toBe(6);   // same month
    expect(runwayDays('2026-06-20', 16)).toBe(26);  // already passed -> next month (Jul 16)
  });
  it('treats cycle day == today as next month (runway >= 1)', () => {
    expect(runwayDays('2026-06-16', 16)).toBe(30);  // Jun 16 -> Jul 16
  });
  it('clamps a 31 cycle day to the target month length', () => {
    expect(runwayDays('2026-02-10', 31)).toBe(18);  // Feb 2026 has 28 days -> Feb 28
  });
});

describe('prettyCard', () => {
  it('upper-cases short bank acronyms and masks to last4', () => {
    expect(prettyCard('sc·3829')).toBe('SC ···3829');
    expect(prettyCard('cimb·4388')).toBe('CIMB ···4388');
    expect(prettyCard('maybank·5161')).toBe('Maybank ···5161');
  });
});

describe('todayMYT', () => {
  it('formats as YYYY-MM-DD in Malaysia time', () => {
    // 2026-06-21 19:00 UTC == 2026-06-22 03:00 MYT
    expect(todayMYT(new Date('2026-06-21T19:00:00Z'))).toBe('2026-06-22');
  });
});

describe('rankCards', () => {
  const cards = ['a·1', 'b·2'];
  const months = ['2026-04', '2026-05', '2026-06'];

  it('ranks the card with the longer float runway higher when load is equal', () => {
    // equal spend -> load tie. From the 10th: a·1 closed on the 9th (just passed ->
    // next bill ~29d away = longest runway); b·2 closes on the 28th (bills in 18d).
    // The just-closed card wins on float.
    const cycles = { 'a·1': 9, 'b·2': 28 };
    const rows = [r('a·1', 'F&B', 100), r('b·2', 'F&B', 100)];
    const out = rankCards({ cards, cycles, rows, months, today: '2026-06-10', nonSpend: NON });
    expect(out[0].card).toBe('a·1');
  });

  it('ranks the under-used card higher when float is equal', () => {
    const cycles = { 'a·1': 16, 'b·2': 16 };   // same cycle -> equal runway
    const rows = [r('a·1', 'F&B', 900), r('b·2', 'F&B', 100)];
    const out = rankCards({ cards, cycles, rows, months, today: '2026-06-01', nonSpend: NON });
    expect(out[0].card).toBe('b·2');   // lower share -> higher loadScore
  });

  it('excludes nonSpend categories and nets refunds from load share', () => {
    const cycles = { 'a·1': 16, 'b·2': 16 };
    const rows = [
      r('a·1', 'F&B', 500), r('a·1', 'Installments/BT', 9999),  // installment ignored
      r('b·2', 'F&B', 500), r('b·2', 'F&B', 400, 1),            // refund nets b·2 down to 100
    ];
    const out = rankCards({ cards, cycles, rows, months, today: '2026-06-01', nonSpend: NON });
    expect(out[0].card).toBe('b·2');   // 100 < 500 share
  });

  it('drops cards with no spend in the trailing 6 months (dormant)', () => {
    const cycles = { 'a·1': 16, 'b·2': 16 };
    const old = ['2025-01', '2025-02', '2025-03', '2025-04', '2025-05', '2025-06', '2026-06'];
    const rows = [r('a·1', 'F&B', 100, 0, '2026-06'), r('b·2', 'F&B', 100, 0, '2025-01')];
    const out = rankCards({ cards, cycles, rows, months: old, today: '2026-06-10', nonSpend: NON });
    expect(out.map((x) => x.card)).toEqual(['a·1']);
  });

  it('skips cards without a known cycle day', () => {
    const cycles = { 'a·1': 16 };   // b·2 has no cycle
    const rows = [r('a·1', 'F&B', 100), r('b·2', 'F&B', 100)];
    const out = rankCards({ cards, cycles, rows, months, today: '2026-06-10', nonSpend: NON });
    expect(out.map((x) => x.card)).toEqual(['a·1']);
  });
});
