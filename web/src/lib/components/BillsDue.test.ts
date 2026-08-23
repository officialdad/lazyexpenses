import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/svelte';
import BillsDue from './BillsDue.svelte';
import type { Bill } from '$lib/types';
import { app } from '$lib/data';
import { push } from '$lib/push.svelte';
import { paid } from '$lib/paid.svelte';

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

  // #85: paid used to only dim + sink the row; the status line went on shouting.
  it('drops the red Overdue line once a bill is paid, and never prints a negative day count', () => {
    paid.keys.add('sc|2026-06');
    try {
      const { container } = render(BillsDue, {
        props: { bills: [bill('sc', '2026-06-17')], today: '2026-06-22' }
      });
      const status = container.querySelector('li [data-urgent]')!;
      expect(status.getAttribute('data-urgent')).toBe('false');
      expect(status.textContent).not.toContain('Overdue');
      expect(status.textContent).not.toContain('-5d');
      expect(container.querySelector('li [style*="#f87171"]')).toBeNull();
    } finally {
      paid.keys.clear();
    }
  });

  it('shows a placeholder when there are no bills', () => {
    const { getByText } = render(BillsDue, { props: { bills: [], today: '2026-06-22' } });
    getByText('No bills yet.');
  });

  // #64: the control used to be underlined 11px text whose only icon was an emoji.
  describe('the reminder control', () => {
    // Pictographic emoji (incl. the old 🔔) live above the BMP or in the misc-symbols block.
    const NO_EMOJI = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
    const BELL_OFF = 'M-off';
    const BELL_ON = 'M-on';
    beforeEach(() => {
      app.icons['bell-outline'] = BELL_OFF;
      app.icons['bell-ring'] = BELL_ON;
    });
    afterEach(() => {
      push.status = 'unknown';
      push.note = '';
    });

    const paths = (c: HTMLElement) =>
      [...c.querySelectorAll('button.remindbtn path')].map((p) => p.getAttribute('d'));

    it('renders a button carrying the MDI bell-outline path, and no emoji anywhere', () => {
      push.status = 'off';
      const { container, getByRole } = render(BillsDue, { props: { bills: [], today: '2026-06-22' } });
      const btn = getByRole('button', { name: /remind me/i });
      expect(btn.getAttribute('aria-pressed')).toBe('false');
      expect(paths(container)).toEqual([BELL_OFF]);
      expect(container.textContent).not.toMatch(NO_EMOJI);
    });

    it('swaps to bell-ring once on, and stays a pressed toggle', () => {
      push.status = 'on';
      const { container, getByRole } = render(BillsDue, { props: { bills: [], today: '2026-06-22' } });
      expect(getByRole('button', { name: /reminders on/i }).getAttribute('aria-pressed')).toBe('true');
      expect(paths(container)).toEqual([BELL_ON]);
      expect(container.textContent).not.toMatch(NO_EMOJI);
    });

    it('shows the note instead of the button when the browser said no', () => {
      push.status = 'denied';
      push.note = 'Notifications are blocked for this site';
      const { container, getByText } = render(BillsDue, { props: { bills: [], today: '2026-06-22' } });
      expect(container.querySelector('button.remindbtn')).toBeNull();
      getByText(/blocked for this site/);
    });
  });
});
