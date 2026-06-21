import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import Dashboard from './Dashboard.svelte';

describe('Dashboard', () => {
  it('renders the three anchor sections and their content', () => {
    const { container, getByText } = render(Dashboard);
    expect(container.querySelector('#overview')).toBeTruthy();
    expect(container.querySelector('#trends')).toBeTruthy();
    expect(container.querySelector('#cuts')).toBeTruthy();
    expect(getByText('Free to spend')).toBeTruthy();   // overview
    expect(getByText('Monthly Spend')).toBeTruthy();    // trends
  });
});
