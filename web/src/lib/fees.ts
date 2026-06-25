import type { Row } from './types';

export type FeeType = 'annual' | 'late' | 'interest';
export const FEE_CAT = 'Fees/Charges';

/** Classify a Fees/Charges description into a tracked fee type, or null to ignore.
 *  Ignored: SST/service tax (govt levy) and one-off gateway charges (IPAY88/GHL/Wise/ONE TIME CHARGE).
 *  Keywords are short + leading, so the 46-char `d` truncation in export can't hide them. */
export function classifyFee(desc: string): FeeType | null {
  const u = desc.toUpperCase();
  if (u.includes('ANNUAL FEE')) return 'annual';
  if (u.includes('LATE PAYMENT') || u.includes('LATE CHARGE')) return 'late';
  if (
    u.includes('FINANCE CHARGE') ||
    u.includes('INTEREST') ||
    u.includes('PROFIT CHRG') ||
    u.includes('PROFIT CHARGE') ||
    u.includes('RTL PROFIT') // Islamic-card "profit" == interest
  )
    return 'interest';
  return null;
}

export interface AnnualFee {
  amount: number;
  month: string; // YYYY-MM of the latest annual-fee debit
  key: string; // waiver-status key: `${card}|${month}`
  reversed: boolean; // a credit offset the charge => auto-waived, not actionable
}

export interface CardFees {
  card: string; // "bank·last4"
  annual: AnnualFee | null;
  late: number; // net late-payment debits (0 when clean)
  interest: number; // net interest/finance debits (0 when clean)
}

export const waiverKey = (card: string, month: string): string => `${card}|${month}`;

const round2 = (n: number) => Math.round(n * 100) / 100;

/** Per-card fee summary across all Fees/Charges rows — one entry per card in `cards`.
 *  Amounts are netted (debit `+`, credit `−`): a reversal cancels the charge. Late/interest
 *  clamp to 0 (a credit ≥ debit means clean). Sorted actionable-annual first, then card name. */
export function feesByCard(rows: Row[], cards: string[]): CardFees[] {
  interface Acc {
    annualNet: number;
    annualLatest: { amount: number; month: string } | null;
    late: number;
    interest: number;
  }
  const acc = new Map<string, Acc>();
  const get = (c: string): Acc => {
    let a = acc.get(c);
    if (!a) {
      a = { annualNet: 0, annualLatest: null, late: 0, interest: 0 };
      acc.set(c, a);
    }
    return a;
  };

  for (const r of rows) {
    if (r.g !== FEE_CAT) continue;
    const ft = classifyFee(r.d);
    if (!ft) continue;
    const signed = r.t === 1 ? -r.a : r.a;
    const a = get(r.c);
    if (ft === 'late') a.late += signed;
    else if (ft === 'interest') a.interest += signed;
    else {
      a.annualNet += signed;
      // latest debit wins (YYYY-MM compares lexically); credits/reversals don't move the marker
      if (r.t === 0 && (!a.annualLatest || r.m > a.annualLatest.month))
        a.annualLatest = { amount: r.a, month: r.m };
    }
  }

  return cards
    .map((card): CardFees => {
      const a = acc.get(card);
      const annual: AnnualFee | null = a?.annualLatest
        ? {
            amount: a.annualLatest.amount,
            month: a.annualLatest.month,
            key: waiverKey(card, a.annualLatest.month),
            reversed: round2(a.annualNet) <= 0
          }
        : null;
      return {
        card,
        annual,
        late: Math.max(0, round2(a?.late ?? 0)),
        interest: Math.max(0, round2(a?.interest ?? 0))
      };
    })
    .sort((x, y) => {
      const ax = x.annual && !x.annual.reversed ? 0 : 1;
      const ay = y.annual && !y.annual.reversed ? 0 : 1;
      if (ax !== ay) return ax - ay;
      return x.card.localeCompare(y.card);
    });
}
