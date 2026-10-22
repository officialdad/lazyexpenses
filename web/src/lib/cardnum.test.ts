import { describe, it, expect, vi, afterEach } from 'vitest';
import { copyToClipboard } from './cardnum';

function setClipboard(value: unknown) {
  Object.defineProperty(navigator, 'clipboard', { value, configurable: true });
}

afterEach(() => {
  setClipboard(undefined);
  vi.restoreAllMocks();
});

describe('copyToClipboard', () => {
  it('uses navigator.clipboard.writeText when the API is present', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard({ writeText });
    expect(await copyToClipboard('1234567890120001')).toBe(true);
    expect(writeText).toHaveBeenCalledWith('1234567890120001');
  });

  // LAN http / tailnet hosts are not a secure context, so navigator.clipboard is undefined.
  it('falls back to execCommand when navigator.clipboard is absent', async () => {
    setClipboard(undefined);
    const exec = vi.fn().mockReturnValue(true);
    (document as unknown as { execCommand: typeof document.execCommand }).execCommand = exec;
    expect(await copyToClipboard('5678')).toBe(true);
    expect(exec).toHaveBeenCalledWith('copy');
  });

  it('falls back when writeText rejects', async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) });
    const exec = vi.fn().mockReturnValue(true);
    (document as unknown as { execCommand: typeof document.execCommand }).execCommand = exec;
    expect(await copyToClipboard('9')).toBe(true);
    expect(exec).toHaveBeenCalledWith('copy');
  });

  it('returns false when every path fails', async () => {
    setClipboard(undefined);
    (document as unknown as { execCommand: typeof document.execCommand }).execCommand = vi
      .fn()
      .mockReturnValue(false);
    expect(await copyToClipboard('x')).toBe(false);
  });
});
