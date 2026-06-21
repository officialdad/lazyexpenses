export function rm(n: number): string {
  const neg = n < 0;
  const s = Math.round(Math.abs(n)).toLocaleString('en-US');
  return (neg ? '-RM' : 'RM') + s;
}
export function pct(n: number): string {
  return Math.round(n * 100) + '%';
}
