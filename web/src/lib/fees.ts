import type { Row } from './types';

export type FeeType = 'annual' | 'late' | 'interest';
export const FEE_CAT = 'Fees/Charges';

/** A waiver/rebate/reversal marker on an annual-fee line. */
const isWaiver = (u: string) => u.includes('WAIVE') || u.includes('REBATE') || u.includes('REVERSAL');

/** Classify a Fees/Charges description into a tracked fee type, or null to ignore.
 *  Ignored: SST/service tax (govt levy) and one-off gateway charges (IPAY88/GHL/Wise/ONE TIME CHARGE).
 *  Keywords are short + leading, so the 46-char `d` truncation in export can't hide them. */
export function classifyFee(desc: string): FeeType | null {
  const u = desc.toUpperCase();
  if (u.includes('ANNUAL FEE') || (u.includes('FEE') && isWaiver(u))) return 'annual';
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
  month: string; // YYYY-MM of the charge (or the waiver line if charged outside our window)
  key: string; // waiver-status key: `${card}|${month}`
  waived: boolean; // reversed in-statement, or an explicit waiver/rebate line exists
}

export interface CardFees {
  card: string; // "bank·last4"
  annual: AnnualFee | null; // null => no annual fee on record for this card
  late: number; // net late-payment debits (0 when clean)
  interest: number; // net interest/finance debits (0 when clean)
}

export const waiverKey = (card: string, month: string): string => `${card}|${month}`;
const round2 = (n: number) => Math.round(n * 100) / 100;

/** Per-card fee summary across all Fees/Charges rows — one entry per card in `cards`.
 *  Amounts are netted (debit `+`, credit `−`). annual: a charge => actionable unless
 *  reversed/waived; a lone waiver line => waived; nothing => null ("none on record").
 *  Sorted actionable-annual first, then card name. */
export function feesByCard(rows: Row[], cards: string[]): CardFees[] {
  interface Acc {
    annualNet: number;
    charge: { amount: number; month: string } | null; // latest real debit
    anyAnnual: { amount: number; month: string } | null; // latest annual row (debit or waiver)
    waived: boolean; // explicit waiver/rebate/reversal line, or a credit, seen
    late: number;
    interest: number;
  }
  const acc = new Map<string, Acc>();
  const get = (k: string): Acc => {
    let a = acc.get(k);
    if (!a) {
      a = { annualNet: 0, charge: null, anyAnnual: null, waived: false, late: 0, interest: 0 };
      acc.set(k, a);
    }
    return a;
  };

  for (const r of rows) {
    if (r.g !== FEE_CAT) continue;
    const ft = classifyFee(r.d);
    if (!ft) continue;
    const a = get(r.c);
    const signed = r.t === 1 ? -r.a : r.a;
    if (ft === 'late') a.late += signed;
    else if (ft === 'interest') a.interest += signed;
    else {
      const u = r.d.toUpperCase();
      a.annualNet += signed;
      if (r.t === 1 || isWaiver(u)) a.waived = true;
      if (!a.anyAnnual || r.m > a.anyAnnual.month) a.anyAnnual = { amount: r.a, month: r.m };
      if (r.t === 0 && !isWaiver(u) && (!a.charge || r.m > a.charge.month))
        a.charge = { amount: r.a, month: r.m };
    }
  }

  return cards
    .map((card): CardFees => {
      const a = acc.get(card);
      let annual: AnnualFee | null = null;
      if (a?.charge) {
        annual = {
          amount: a.charge.amount,
          month: a.charge.month,
          key: waiverKey(card, a.charge.month),
          waived: round2(a.annualNet) <= 0 || a.waived
        };
      } else if (a?.waived && a.anyAnnual) {
        // waiver/rebate line with no visible charge in the collected window
        annual = {
          amount: a.anyAnnual.amount,
          month: a.anyAnnual.month,
          key: waiverKey(card, a.anyAnnual.month),
          waived: true
        };
      }
      return {
        card,
        annual,
        late: Math.max(0, round2(a?.late ?? 0)),
        interest: Math.max(0, round2(a?.interest ?? 0))
      };
    })
    .sort((x, y) => {
      const ax = x.annual && !x.annual.waived ? 0 : 1;
      const ay = y.annual && !y.annual.waived ? 0 : 1;
      if (ax !== ay) return ax - ay;
      return x.card.localeCompare(y.card);
    });
}
