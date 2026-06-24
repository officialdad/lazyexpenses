// Per-bank accent for the home-page card icons. Brand-approximate but picked for
// distinct hues on the black bg (cimb/hsbc/alliance brands all skew red IRL).
export const BANK_COLOR: Record<string, string> = {
  maybank: '#F5B400', // yellow
  cimb: '#16A34A', // green
  sc: '#2563EB', // blue
  alliance: '#22D3EE', // cyan
  hsbc: '#DB0011', // red
  rhb: '#EC4899' // pink
};

export const bankColor = (bank: string): string => BANK_COLOR[bank] ?? 'var(--muted)';

/** MDI icon name (already shipped in app.json) used for every card/bill row. */
export const CARD_ICON = 'credit-card-outline';
