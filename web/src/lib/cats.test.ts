import { describe, it, expect, beforeEach } from 'vitest';
import { cats } from './cats.svelte';

const ok = (body: unknown) =>
  Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);

describe('cats store (#82)', () => {
  // Module-level singleton — reset to empty before each test.
  beforeEach(async () => {
    await cats.load((() => ok({})) as unknown as typeof fetch);
  });

  it('hydrates confirmations from the server', async () => {
    await cats.load((() => ok({ 'SEIROCK-YA': 'F&B' })) as unknown as typeof fetch);
    expect(cats.category('SEIROCK-YA')).toBe('F&B');
    expect(cats.category('BINGXUE')).toBe('');
  });

  it('confirms a merchant, then clears it back to Other', async () => {
    const sent: unknown[] = [];
    const f = ((_url: string, init?: RequestInit) => {
      sent.push(JSON.parse(String(init?.body)));
      return ok({});
    }) as unknown as typeof fetch;
    expect(await cats.set('BINGXUE', 'F&B', f)).toBe(true);
    expect(cats.category('BINGXUE')).toBe('F&B');
    expect(sent[0]).toEqual({ merchant: 'BINGXUE', category: 'F&B' });
    // Clearing is the only way a bad confirmation is undone — CATS cannot override it.
    expect(await cats.set('BINGXUE', '', f)).toBe(true);
    expect(cats.category('BINGXUE')).toBe('');
    expect(sent[1]).toEqual({ merchant: 'BINGXUE', category: null });
  });

  it('reverts the optimistic change when the write fails', async () => {
    const fail = (() => Promise.resolve({ ok: false, status: 500 } as Response)) as unknown as typeof fetch;
    expect(await cats.set('THAI CUISINE', 'F&B', fail)).toBe(false);
    expect(cats.category('THAI CUISINE')).toBe('');
  });
});
