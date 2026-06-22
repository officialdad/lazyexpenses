import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import CardPick from './CardPick.svelte';

describe('CardPick', () => {
  it('renders the section heading and a recommended card after mount', async () => {
    const { container, findAllByText } = render(CardPick);
    expect(container.querySelector('section[aria-label="Which card to use next"]')).toBeTruthy();
    // onMount resolves today -> a real card label (masked) appears
    const items = await findAllByText(/···/);
    expect(items.length).toBeGreaterThan(0);
  });
});
