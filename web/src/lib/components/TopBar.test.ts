import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import TopBar from './TopBar.svelte';

describe('TopBar', () => {
  it('renders brand + three anchor links', () => {
    const { getByText, container } = render(TopBar);
    expect(getByText('CC')).toBeTruthy();
    expect(getByText('Overview')).toBeTruthy();
    expect(getByText('Trends')).toBeTruthy();
    expect(getByText('Cuts')).toBeTruthy();
    expect(container.querySelector('a[href="#overview"]')).toBeTruthy();
    expect(container.querySelector('a[href="#trends"]')).toBeTruthy();
    expect(container.querySelector('a[href="#cuts"]')).toBeTruthy();
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
