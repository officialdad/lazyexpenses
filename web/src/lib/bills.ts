import type { Bill } from './types';

export interface BillRow extends Bill {
  days: number | null;
  urgent: boolean;
  paid: boolean;
}

/** Red when strictly fewer than this many days remain (so 0/1/2 days and overdue are urgent; 3+ is not). */
export const URGENT_DAYS = 3;

/** Whole days from `today` to `due` (both 'YYYY-MM-DD'). Negative = overdue; null if `due` is null. */
export function daysUntil(due: string | null, today: string): number | null {
  if (!due) return null;
  const [ty, tm, td] = today.split('-').map(Number);
  const [dy, dm, dd] = due.split('-').map(Number);
  const t = Date.UTC(ty, tm - 1, td);
  const d = Date.UTC(dy, dm - 1, dd);
  return Math.round((d - t) / 86_400_000);
}

/** Annotate bills with days-until + urgent + paid, sorted unpaid-first then by due date
 *  ascending (null due dates last). `paidKeys` holds `bank|statement_month` keys. */
export function sortBills(bills: Bill[], today: string, paidKeys?: ReadonlySet<string>): BillRow[] {
  return bills
    .map((b) => {
      const days = daysUntil(b.payment_due_date, today);
      const paid = paidKeys?.has(`${b.bank}|${b.statement_month}`) ?? false;
      return { ...b, days, urgent: days !== null && days < URGENT_DAYS, paid };
    })
    .sort((a, b) => {
      if (a.paid !== b.paid) return a.paid ? 1 : -1; // paid bills sink to the bottom
      if (a.days === null) return b.days === null ? 0 : 1;
      if (b.days === null) return -1;
      return a.days - b.days;
    });
}
