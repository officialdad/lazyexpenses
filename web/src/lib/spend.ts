import type { Row } from './types';

const round2 = (n: number) => Math.round(n * 100) / 100;

export function cashbackFor(rows: Row[], month: string): number {
  let s = 0;
  for (const r of rows) if (r.m === month && r.g === 'Rebate/Cashback' && r.t === 1) s += r.a;
  return round2(s);
}

export function discretionaryTotal(rows: Row[], month: string, nonSpend: string[]): number {
  const skip = new Set(nonSpend);
  let s = 0;
  for (const r of rows) {
    if (r.m !== month || skip.has(r.g)) continue;
    s += r.t === 0 ? r.a : -r.a;
  }
  return round2(s);
}

export function prevMonth(months: string[], month: string): string | null {
  const i = months.indexOf(month);
  return i > 0 ? months[i - 1] : null;
}
