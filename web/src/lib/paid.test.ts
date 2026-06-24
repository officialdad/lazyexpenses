import { describe, it, expect, beforeEach } from 'vitest';
import { paid } from './paid.svelte';

const ok = (body: unknown) =>
  Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);

describe('paid store', () => {
  // Module-level singleton — reset to empty before each test.
  beforeEach(async () => {
    await paid.load((() => ok([])) as unknown as typeof fetch);
  });

  it('hydrates keys from the server', async () => {
    await paid.load((() => ok(['cimb|2026-06'])) as unknown as typeof fetch);
    expect(paid.has('cimb', '2026-06')).toBe(true);
    expect(paid.has('hsbc', '2026-06')).toBe(false);
  });

  it('toggles on then off, posting each change', async () => {
    const sent: unknown[] = [];
    const f = ((_url: string, init?: RequestInit) => {
      sent.push(JSON.parse(String(init?.body)));
      return ok({});
    }) as unknown as typeof fetch;
    await paid.toggle('sc', '2026-06', f);
    expect(paid.has('sc', '2026-06')).toBe(true);
    expect(sent[0]).toEqual({ key: 'sc|2026-06', paid: true });
    await paid.toggle('sc', '2026-06', f);
    expect(paid.has('sc', '2026-06')).toBe(false);
    expect(sent[1]).toEqual({ key: 'sc|2026-06', paid: false });
  });

  it('reverts the optimistic change when the write fails', async () => {
    const fail = (() => Promise.resolve({ ok: false, status: 500 } as Response)) as unknown as typeof fetch;
    await paid.toggle('rhb', '2026-06', fail);
    expect(paid.has('rhb', '2026-06')).toBe(false);
  });
});
