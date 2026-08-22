import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import Icon from './Icon.svelte';
import { app } from '$lib/data';

describe('Icon', () => {
  it('draws the named path from the runtime icon table', () => {
    app.icons['cart'] = 'M-cart';
    const { container } = render(Icon, { props: { name: 'cart' } });
    expect(container.querySelector('path')!.getAttribute('d')).toBe('M-cart');
  });

  // #64: app.json is only rewritten when the pipeline runs, so a UI that ships a new icon
  // name renders against a stale table. That used to be an invisible icon and no clue why.
  it('falls back to a visible box for a name the table does not have', () => {
    const { container } = render(Icon, { props: { name: 'no-such-icon' } });
    expect(container.querySelector('path')!.getAttribute('d')).toBeTruthy();
  });
});
