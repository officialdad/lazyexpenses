import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/svelte';
import TopBar from './TopBar.svelte';

describe('TopBar', () => {
  it('renders brand + three anchor links', () => {
    const { getByText, container } = render(TopBar);
    expect(getByText('CC')).toBeTruthy();
    expect(getByText('Overview')).toBeTruthy();
    expect(getByText('Trends')).toBeTruthy();
    expect(getByText('Cuts')).toBeTruthy();
    expect(container.querySelector('a[href="#overview"]')).toBeTruthy();
    expect(container.querySelector('a[href="#trends"]')).toBeTruthy();
    expect(container.querySelector('a[href="#cuts"]')).toBeTruthy();
  });
});
