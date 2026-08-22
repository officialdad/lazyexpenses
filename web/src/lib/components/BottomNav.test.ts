import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import BottomNav from './BottomNav.svelte';

describe('BottomNav', () => {
  // #66: settings used to be an 11px text link in a header that scrolls away. The bottom
  // nav is the only chrome a phone user learns, so the tab is what makes it findable.
  it('has a Settings tab pointing at /settings', () => {
    const { container, getByText } = render(BottomNav);
    expect(container.querySelector('a[href="/settings"]')).toBeTruthy();
    expect(getByText('Settings')).toBeTruthy();
  });
});
