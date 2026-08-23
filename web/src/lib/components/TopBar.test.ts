import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import TopBar from './TopBar.svelte';

describe('TopBar', () => {
  it('renders brand + three anchor links', () => {
    const { getByText, container } = render(TopBar);
    expect(getByText('lazyexpenses')).toBeTruthy();
    expect(getByText('Overview')).toBeTruthy();
    expect(getByText('Trends')).toBeTruthy();
    expect(getByText('Cuts')).toBeTruthy();
    expect(container.querySelector('a[href="/#overview"]')).toBeTruthy();
    expect(container.querySelector('a[href="/#trends"]')).toBeTruthy();
    expect(container.querySelector('a[href="/#cuts"]')).toBeTruthy();
  });

  // #86: TopBar renders on /settings too, where no such section exists. A click that is
  // swallowed there leaves the link dead, so the href has to be allowed to navigate.
  it('lets a click through when the section is not on the page', async () => {
    const { container } = render(TopBar);
    const a = container.querySelector('a[href="/#trends"]')! as HTMLAnchorElement;
    const ev = new MouseEvent('click', { bubbles: true, cancelable: true });
    a.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(false);
  });

  // #66: an icon with no text needs an accessible name, or the control is unreachable
  // for anyone not looking at it.
  it('links to /settings as an icon button with an accessible name', () => {
    const { container } = render(TopBar);
    const a = container.querySelector('a[href="/settings"]')!;
    expect(a.getAttribute('aria-label')).toBe('Settings');
    expect(a.querySelector('svg path')).toBeTruthy();
    expect(a.textContent!.trim()).toBe('');
  });
});
