import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import BillsDue from './BillsDue.svelte';
import type { Bill } from '$lib/types';

const bill = (bank: string, due: string | null, bal: number | null = 100): Bill => ({
  bank,
  statement_month: '2026-06',
  current_balance: bal,
  payment_due_date: due,
  minimum_payment: null,
});

describe('BillsDue', () => {
  it('renders one row per bill, soonest first, with the urgent due styled red', () => {
    const bills = [bill('cimb', '2026-06-25'), bill('sc', '2026-06-23')];
    const { container, getByText } = render(BillsDue, { props: { bills, today: '2026-06-22' } });
    expect(container.querySelector('section[aria-label="Bills due"]')).toBeTruthy();
    const items = container.querySelectorAll('li');
    expect(items.length).toBe(2);
    // sc is due in 1 day -> sorted first AND urgent (red token present)
    expect(items[0].textContent).toContain('SC');
    // Check for the red color (Svelte/browser converts #f87171 to rgb(248, 113, 113))
    expect(items[0].querySelector('[style*="rgb(248, 113, 113)"]')).toBeTruthy();
    // cimb is due in 3 days -> not urgent (no red token)
    expect(items[1].querySelector('[style*="rgb(248, 113, 113)"]')).toBeFalsy();
    getByText(/CIMB/);
  });

  it('shows a placeholder when there are no bills', () => {
    const { getByText } = render(BillsDue, { props: { bills: [], today: '2026-06-22' } });
    getByText('No bills yet.');
  });
});
