import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import OverviewView from './OverviewView.svelte';
import TrendsView from './TrendsView.svelte';
import CutsView from './CutsView.svelte';

describe('View components render', () => {
  it('OverviewView shows the headroom hero', () => {
    const { getByText } = render(OverviewView);
    expect(getByText('Free to spend')).toBeTruthy();
  });
  it('TrendsView shows all three chart headers', () => {
    const { getByText } = render(TrendsView);
    expect(getByText('Monthly Spend')).toBeTruthy();
    expect(getByText('Spend by Category')).toBeTruthy();
    expect(getByText('Top 20 Merchants')).toBeTruthy();
  });
  it('CutsView renders without throwing and shows the Cuts label', () => {
    const { getByText } = render(CutsView);
    expect(getByText('Cuts')).toBeTruthy();
  });
});
