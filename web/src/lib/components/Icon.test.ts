import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import Icon from './Icon.svelte';
import { app } from '$lib/data';
import fixture from '../../../static/data/app.json';

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

  // #66: the fallback above means a missing icon is visible but not loud. This is the
  // loud half — every name the UI hardcodes must actually be in dashboard.py's MDI dict,
  // which is what export_data.py ships as app.json's "icons".
  it('ships every icon name the chrome hardcodes', () => {
    for (const n of ['wallet-outline', 'chart-line', 'content-cut', 'receipt-text-outline', 'cog-outline'])
      expect(fixture.icons, n).toHaveProperty(n);
  });
});
