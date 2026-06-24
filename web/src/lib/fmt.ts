export function rm(n: number, cents = false): string {
  const neg = n < 0;
  const s = cents
    ? Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : Math.round(Math.abs(n)).toLocaleString('en-US');
  return (neg ? '-RM' : 'RM') + s;
}
export function pct(n: number): string {
  return Math.round(n * 100) + '%';
}
export function kRM(n: number): string {
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  if (abs < 1000) return sign + Math.round(abs).toString();
  const k = abs / 1000;
  const s = k >= 100 ? Math.round(k).toString() : k.toFixed(1).replace(/\.0$/, '');
  return sign + s + 'k';
}

// Month formatting for 'YYYY-MM' keys — shared by the trend bars, donut, and merchants.
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
export const moName = (m: string) => MONTHS[parseInt(m.split('-')[1], 10) - 1] ?? m;
export const yr2 = (m: string) => "'" + (m.split('-')[0]?.slice(2) ?? '');
export const monthLabel = (m: string) => `${moName(m)} ${yr2(m)}`;
