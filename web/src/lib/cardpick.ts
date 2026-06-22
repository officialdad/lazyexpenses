import type { Row } from './types';

export interface CardRank {
  card: string;
  runwayDays: number;
  floatScore: number;
  share: number;
  loadScore: number;
  score: number;
  why: string;
}

export const FLOAT_W = 0.5;       // blend weight for float; load weight = 1 - FLOAT_W
export const DORMANT_MONTHS = 6;  // candidate must have spend within this trailing window

/** "YYYY-MM-DD" in Malaysia time (GMT+8), regardless of device tz. */
export function todayMYT(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kuala_Lumpur' }).format(now);
}

/** "alliance·4963" -> "Alliance ···4963"; short bank names upper-cased. */
export function prettyCard(c: string): string {
  const [bank = c, last4 = ''] = c.split('·');
  const label = bank.length <= 4 ? bank.toUpperCase() : bank[0].toUpperCase() + bank.slice(1);
  return last4 ? `${label} ···${last4}` : label;
}

const lastDay = (year: number, month0: number) => new Date(Date.UTC(year, month0 + 1, 0)).getUTCDate();
const clampDay = (year: number, month0: number, day: number) => Math.min(day, lastDay(year, month0));

/** Days from `today` (YYYY-MM-DD) until the next occurrence of day-of-month `cycleDay`, strictly after today. >= 1. */
export function runwayDays(today: string, cycleDay: number): number {
  const [y, m, d] = today.split('-').map(Number);
  const todayUTC = Date.UTC(y, m - 1, d);
  let yy = y, mm = m - 1;                       // mm is 0-based
  let cand = Date.UTC(yy, mm, clampDay(yy, mm, cycleDay));
  if (cand <= todayUTC) {
    mm += 1;
    if (mm > 11) { mm = 0; yy += 1; }
    cand = Date.UTC(yy, mm, clampDay(yy, mm, cycleDay));
  }
  return Math.round((cand - todayUTC) / 86_400_000);
}

function lastN(months: string[], n: number): Set<string> {
  return new Set(months.slice(Math.max(0, months.length - n)));
}

function spendByCard(rows: Row[], inMonths: Set<string>, skip: Set<string>): Map<string, number> {
  const m = new Map<string, number>();
  for (const row of rows) {
    if (!inMonths.has(row.m) || skip.has(row.g)) continue;
    m.set(row.c, (m.get(row.c) ?? 0) + (row.t === 0 ? row.a : -row.a));
  }
  return m;
}

export function rankCards(p: {
  cards: string[];
  cycles: Record<string, number>;
  rows: Row[];
  months: string[];
  today: string;
  nonSpend: string[];
}): CardRank[] {
  const skip = new Set(p.nonSpend);
  const last3 = lastN(p.months, 3);
  const last6 = lastN(p.months, DORMANT_MONTHS);
  const spend6 = spendByCard(p.rows, last6, skip);
  const spend3 = spendByCard(p.rows, last3, skip);

  const cands = p.cards.filter((c) => p.cycles[c] != null && (spend6.get(c) ?? 0) > 0);
  if (!cands.length) return [];

  const runway = new Map(cands.map((c) => [c, runwayDays(p.today, p.cycles[c])]));
  const maxRun = Math.max(...runway.values());

  const pos = (c: string) => Math.max(0, spend3.get(c) ?? 0);
  const total = cands.reduce((s, c) => s + pos(c), 0);
  const shareOf = (c: string) => (total > 0 ? pos(c) / total : 0);
  const shares = cands.map(shareOf);
  const maxShare = Math.max(...shares), minShare = Math.min(...shares);
  const span = maxShare - minShare;

  const ranked: CardRank[] = cands.map((c) => {
    const rd = runway.get(c)!;
    const floatScore = maxRun > 0 ? rd / maxRun : 0;
    const share = shareOf(c);
    const loadScore = span > 0 ? (maxShare - share) / span : 1;
    const score = FLOAT_W * floatScore + (1 - FLOAT_W) * loadScore;
    const why = floatScore >= loadScore ? `longest runway, ${rd} days` : `least-used lately, ${Math.round(share * 100)}%`;
    return { card: c, runwayDays: rd, floatScore, share, loadScore, score, why };
  });

  ranked.sort((a, b) => b.score - a.score || b.runwayDays - a.runwayDays);
  return ranked;
}
