// Pure 3-day-window filter for the bills reminder. The n8n Code node pastes the
// body of billsDueIn() inline (n8n can't import local files). Date math is on
// calendar dates only (no time-of-day): add `days` to todayISO, string-compare.
export function addDaysISO(iso, days) {
  // iso = "YYYY-MM-DD". Use UTC to avoid host-timezone drift; we only care about
  // the calendar date, and the caller passes a KL wall-date for today.
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + days);
  const yyyy = dt.getUTCFullYear();
  const mm = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(dt.getUTCDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

export function billsDueIn(bills, todayISO, days = 3) {
  const target = addDaysISO(todayISO, days);
  return (bills || []).filter((b) => b && b.payment_due_date === target);
}
