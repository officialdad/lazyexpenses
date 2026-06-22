export interface Row { c: string; m: string; g: string; a: number; t: 0 | 1; d: string; }
export interface CommitItem { name: string; monthly: number; kind: 'sub' | 'installment'; }
export interface Committed { monthly: number; subs: number; installments: number; subCats: string[]; items: CommitItem[]; }
export interface Bill {
  bank: string;
  statement_month: string;
  current_balance: number | null;
  payment_due_date: string | null;
  minimum_payment: number | null;
}
export interface AppData {
  rows: Row[]; months: string[]; cards: string[]; cats: string[]; nonSpend: string[];
  colors: Record<string, string>; catIcon: Record<string, string>; icons: Record<string, string>;
  range: string; recs: any[]; installments: any[]; transfers: any[]; committed: Committed;
  cycles: Record<string, number>; bills: Bill[];
}
