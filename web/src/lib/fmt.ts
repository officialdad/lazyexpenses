export function rm(n: number): string {
  const neg = n < 0;
  const s = Math.round(Math.abs(n)).toLocaleString('en-US');
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
