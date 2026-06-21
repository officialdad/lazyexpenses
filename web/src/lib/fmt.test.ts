import { describe, it, expect } from 'vitest';
import { rm, pct, kRM } from './fmt';

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

describe('kRM compact', () => {
  it('renders sub-1000 verbatim, no k', () => {
    expect(kRM(0)).toBe('0');
    expect(kRM(939)).toBe('939');
    expect(kRM(999)).toBe('999');
  });
  it('renders thousands with one decimal, trimming .0', () => {
    expect(kRM(1000)).toBe('1k');
    expect(kRM(1499)).toBe('1.5k');
    expect(kRM(6606)).toBe('6.6k');
    expect(kRM(15234)).toBe('15.2k');
  });
  it('drops the decimal at >=100k', () => {
    expect(kRM(123456)).toBe('123k');
  });
  it('keeps the sign', () => {
    expect(kRM(-6606)).toBe('-6.6k');
  });
});
