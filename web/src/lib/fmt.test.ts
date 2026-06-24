import { describe, it, expect } from 'vitest';
import { rm, pct, kRM, ago } from './fmt';

describe('fmt', () => {
  it('formats ringgit with separators, no decimals', () => {
    expect(rm(1234.56)).toBe('RM1,235');
    expect(rm(860)).toBe('RM860');
    expect(rm(-140)).toBe('-RM140');
  });
  it('formats exact cents when asked; default stays rounded', () => {
    expect(rm(1234.5, true)).toBe('RM1,234.50');
    expect(rm(2431.2, true)).toBe('RM2,431.20');
    expect(rm(-140.05, true)).toBe('-RM140.05');
    expect(rm(860, true)).toBe('RM860.00');
    expect(rm(1234.56)).toBe('RM1,235'); // default path unchanged
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

describe('ago relative time', () => {
  const t = 1_000_000_000_000;
  it('handles the never/just-now edges', () => {
    expect(ago(0, t)).toBe('never');
    expect(ago(t, t)).toBe('just now');
    expect(ago(t - 30_000, t)).toBe('just now');
  });
  it('renders minutes, hours, and days', () => {
    expect(ago(t - 5 * 60_000, t)).toBe('5m ago');
    expect(ago(t - 3 * 3_600_000, t)).toBe('3h ago');
    expect(ago(t - 2 * 86_400_000, t)).toBe('2d ago');
  });
});
