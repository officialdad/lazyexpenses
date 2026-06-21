import { describe, it, expect } from 'vitest';
import { rm, pct } from './fmt';

describe('fmt', () => {
  it('formats ringgit with separators, no decimals', () => {
    expect(rm(1234.56)).toBe('RM1,235');
    expect(rm(860)).toBe('RM860');
    expect(rm(-140)).toBe('-RM140');
  });
  it('formats percent', () => {
    expect(pct(0.713)).toBe('71%');
  });
});
