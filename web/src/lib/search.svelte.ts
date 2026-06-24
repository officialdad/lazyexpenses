import type { Row } from './types';

// Global open/close flag for the search overlay, toggled from both navs.
export const search = $state({ open: false });

// MDI "magnify" path — not in the server-generated app.icons dict, so inlined here
// for the nav triggers and the overlay input.
export const MAGNIFY =
  'M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z';

export const LIMIT = 100;

export interface SearchResult {
  rows: Row[];
  total: number;
}

// ponytail: case-insensitive substring over description / category / card / amount —
// NOT fuzzy. Upgrade to fuse.js only if typo-tolerance is actually wanted.
export function filterRows(rows: Row[], q: string, limit = LIMIT): SearchResult {
  const needle = q.trim().toLowerCase();
  if (!needle) return { rows: [], total: 0 };
  const hits = rows.filter(
    (r) =>
      r.d.toLowerCase().includes(needle) ||
      r.g.toLowerCase().includes(needle) ||
      r.c.toLowerCase().includes(needle) ||
      String(r.a).includes(needle)
  );
  // Newest month first, then larger amount within a month.
  hits.sort((a, b) => (a.m < b.m ? 1 : a.m > b.m ? -1 : b.a - a.a));
  return { rows: hits.slice(0, limit), total: hits.length };
}
