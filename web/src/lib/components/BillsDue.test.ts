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
    // sc is due in 1 day -> sorted first AND urgent
    expect(items[0].textContent).toContain('SC');
    // Check urgent state via data-urgent attribute (stable, not dependent on computed color)
    expect(items[0].querySelector('[data-urgent="true"]')).toBeTruthy();
    // The soonest (urgent) row should show its day suffix
    expect(items[0].querySelector('[data-urgent="true"]')!.textContent).toContain('1d');
    // cimb is due in 3 days -> not urgent
    expect(items[1].querySelector('[data-urgent="false"]')).toBeTruthy();
    getByText(/CIMB/);
  });

  it('shows a placeholder when there are no bills', () => {
    const { getByText } = render(BillsDue, { props: { bills: [], today: '2026-06-22' } });
    getByText('No bills yet.');
  });
});
