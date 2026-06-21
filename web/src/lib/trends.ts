import type { Row } from './types';
const round2 = (n: number) => Math.round(n * 100) / 100;
const val = (r: Row) => (r.t === 0 ? r.a : -r.a);

export function monthlySeries(rows: Row[], months: string[], nonSpend: string[]) {
  const skip = new Set(nonSpend);
  const acc = new Map<string, number>(months.map((m) => [m, 0]));
  for (const r of rows) if (!skip.has(r.g) && acc.has(r.m)) acc.set(r.m, acc.get(r.m)! + val(r));
  return months.map((m) => ({ month: m, total: round2(acc.get(m)!) }));
}

export function byCategory(rows: Row[], month: string | null, nonSpend: string[]) {
  const skip = new Set(nonSpend);
  const acc = new Map<string, number>();
  for (const r of rows) {
    if (skip.has(r.g)) continue;
    if (month && r.m !== month) continue;
    acc.set(r.g, (acc.get(r.g) ?? 0) + val(r));
  }
  return [...acc].map(([g, total]) => ({ g, total: round2(total) }))
    .filter((x) => x.total > 0).sort((a, b) => b.total - a.total);
}

export function topMerchants(rows: Row[], n: number, nonSpend: string[]) {
  const skip = new Set(nonSpend);
  const acc = new Map<string, number>();
  for (const r of rows) {
    if (skip.has(r.g)) continue;
    acc.set(r.d, (acc.get(r.d) ?? 0) + val(r));
  }
  return [...acc].map(([d, total]) => ({ d, total: round2(total) }))
    .filter((x) => x.total > 0).sort((a, b) => b.total - a.total).slice(0, n);
}
