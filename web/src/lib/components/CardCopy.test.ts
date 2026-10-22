import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/svelte';
import CardCopy from './CardCopy.svelte';
import { app } from '$lib/data';

beforeEach(() => {
  app.cardNumbers = {};
});

describe('CardCopy', () => {
  it('renders nothing when the card has no full number (masked statement)', () => {
    const { container } = render(CardCopy, { props: { card: 'sc·0004' } });
    expect(container.querySelector('button.cardcopy')).toBeNull();
  });

  it('renders a copy button, labelled with the masked card, when a number is available', () => {
    app.cardNumbers = { 'maybank·0001': '1234567890120001' };
    const { container } = render(CardCopy, { props: { card: 'maybank·0001' } });
    const btn = container.querySelector('button.cardcopy');
    expect(btn).toBeTruthy();
    expect(btn!.getAttribute('aria-label')).toContain('Maybank ···0001');
  });
});
