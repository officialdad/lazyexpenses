import { describe, it, expect } from 'vitest';
import { filterRows } from './search.svelte';
import type { Row } from './types';

const row = (over: Partial<Row>): Row => ({
  c: 'cimb·1234',
  m: '2026-01',
  g: 'Shopping',
  a: 10,
  t: 0,
  d: 'GENERIC',
  ...over
});

describe('filterRows', () => {
  it('matches description case-insensitively', () => {
    const rows = [row({ d: 'SHOPEE PAYMENT' }), row({ d: 'GRAB RIDE' })];
    expect(filterRows(rows, 'shopee').rows).toHaveLength(1);
    expect(filterRows(rows, 'SHOPEE').rows[0].d).toBe('SHOPEE PAYMENT');
  });

  it('matches by amount and by category', () => {
    const rows = [row({ a: 199.5, d: 'A' }), row({ g: 'Groceries', d: 'B' })];
    expect(filterRows(rows, '199.5').rows[0].d).toBe('A');
    expect(filterRows(rows, 'grocer').rows[0].d).toBe('B');
  });

  it('returns nothing for a blank query', () => {
    expect(filterRows([row({})], '   ').rows).toHaveLength(0);
    expect(filterRows([row({})], '   ').total).toBe(0);
  });

  it('caps results but reports the true total', () => {
    const rows = Array.from({ length: 150 }, (_, i) => row({ d: `TXN ${i}` }));
    const res = filterRows(rows, 'txn', 100);
    expect(res.rows).toHaveLength(100);
    expect(res.total).toBe(150);
  });

  it('sorts newest month first', () => {
    const rows = [row({ m: '2025-12', d: 'PItem' }), row({ m: '2026-06', d: 'PItem' })];
    expect(filterRows(rows, 'pitem').rows.map((r) => r.m)).toEqual(['2026-06', '2025-12']);
  });
});
