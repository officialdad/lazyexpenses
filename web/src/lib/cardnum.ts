/** Clipboard write, with a fallback for origins where `navigator.clipboard` is absent.
 *
 *  This app is often reached over plain-HTTP LAN or a tailnet host, and the async
 *  Clipboard API only exists in a secure context (HTTPS or localhost) — so on those
 *  origins `navigator.clipboard` is undefined. The `execCommand('copy')` path covers
 *  them. Returns true on success, false if both paths fail; never throws. */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // fall through to execCommand (permission denied, not focused, …)
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '-9999px';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    ta.remove();
    return ok;
  } catch {
    return false;
  }
}
