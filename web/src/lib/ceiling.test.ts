import { describe, it, expect, beforeEach, vi } from 'vitest';

describe('ceiling store', () => {
  beforeEach(() => { localStorage.clear(); vi.resetModules(); });

  it('defaults to 3000 when unset', async () => {
    const { ceiling } = await import('./ceiling.svelte');
    expect(ceiling.value).toBe(3000);
  });

  it('persists a set value', async () => {
    const { ceiling } = await import('./ceiling.svelte');
    ceiling.set(2500);
    expect(ceiling.value).toBe(2500);
    expect(localStorage.getItem('cc.ceiling')).toBe('2500');
  });
});
