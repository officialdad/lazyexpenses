import type { Row, Committed } from './types';

export type Status = 'ok' | 'warn' | 'over';
export interface Headroom { locked: number; spent: number; free: number; used: number; pct: number; status: Status; }

const round2 = (n: number) => Math.round(n * 100) / 100;

export function computeHeadroom(p: {
  rows: Row[]; month: string; ceiling: number; committed: Committed; nonSpend: string[];
}): Headroom {
  const skip = new Set([...p.nonSpend, 'Subscriptions']);
  let spent = 0;
  for (const row of p.rows) {
    if (row.m !== p.month) continue;
    if (skip.has(row.g)) continue;
    spent += row.t === 0 ? row.a : -row.a;          // net refunds
  }
  spent = round2(spent);
  const locked = round2(p.committed.monthly);
  const used = round2(locked + spent);
  const free = round2(p.ceiling - used);
  const pct = p.ceiling > 0 ? used / p.ceiling : 0;
  const status: Status = used > p.ceiling ? 'over' : free < p.ceiling * 0.1 ? 'warn' : 'ok';
  return { locked, spent, free, used, pct, status };
}
