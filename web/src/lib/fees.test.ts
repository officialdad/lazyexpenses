import { describe, it, expect } from 'vitest';
import { classifyFee, feesByCard, waiverKey } from './fees';
import type { Row } from './types';

const row = (c: string, m: string, d: string, a: number, t: 0 | 1 = 0): Row => ({
  c,
  m,
  g: 'Fees/Charges',
  a,
  t,
  d
});

describe('classifyFee', () => {
  it('annual (case-insensitive) + waiver/rebate lines', () => {
    expect(classifyFee('ANNUAL FEE')).toBe('annual');
    expect(classifyFee('Annual Fee')).toBe('annual');
    expect(classifyFee('ANNUAL FEE WAIVER')).toBe('annual');
    expect(classifyFee('FEE REBATE')).toBe('annual');
  });
  it('late', () => {
    expect(classifyFee('LATE PAYMENT CHARGE')).toBe('late');
    expect(classifyFee('LATE CHARGE')).toBe('late');
  });
  it('interest / finance / Islamic profit', () => {
    expect(classifyFee('FINANCE CHARGE')).toBe('interest');
    expect(classifyFee('INTEREST')).toBe('interest');
    expect(classifyFee('RTL PROFIT CHRG')).toBe('interest');
  });
  it('ignores SST and one-off gateway charges', () => {
    expect(classifyFee('SERVICE TAX')).toBeNull();
    expect(classifyFee('CC SERVICE TAX(SST ID:W10-1808-32000842)')).toBeNull();
    expect(classifyFee('ONE TIME CHARGE')).toBeNull();
    expect(classifyFee('IPAY88*KLIAEKSPRES KUALA LUMPUR')).toBeNull();
  });
});

describe('feesByCard', () => {
  it('surfaces an actionable annual fee with a stable key', () => {
    const res = feesByCard([row('sc·3829', '2026-02', 'ANNUAL FEE', 250)], ['sc·3829']);
    expect(res[0].annual).toEqual({
      amount: 250,
      month: '2026-02',
      key: waiverKey('sc·3829', '2026-02'),
      waived: false
    });
    expect(res[0].late).toBe(0);
    expect(res[0].interest).toBe(0);
  });

  it('marks annual waived when a credit reverses it', () => {
    const res = feesByCard(
      [row('x·1', '2026-02', 'ANNUAL FEE', 148), row('x·1', '2026-03', 'ANNUAL FEE REVERSAL', 148, 1)],
      ['x·1']
    );
    expect(res[0].annual?.waived).toBe(true);
    expect(res[0].annual?.month).toBe('2026-02'); // marker stays on the charge
  });

  it('marks waived from a lone waiver line (charge outside the window)', () => {
    const res = feesByCard([row('x·1', '2026-02', 'ANNUAL FEE WAIVER', 0, 1)], ['x·1']);
    expect(res[0].annual?.waived).toBe(true);
  });

  it('null annual when no fee on record (=> "none on record", not "no fee")', () => {
    const res = feesByCard([row('x·1', '2026-02', 'SERVICE TAX', 25)], ['x·1']);
    expect(res[0].annual).toBeNull();
  });

  it('keeps every card separate (one entry per card)', () => {
    const res = feesByCard(
      [row('alliance·4963', '2026-02', 'ANNUAL FEE', 148)],
      ['alliance·4963', 'alliance·8272']
    );
    expect(res).toHaveLength(2);
    expect(res.map((r) => r.card).sort()).toEqual(['alliance·4963', 'alliance·8272']);
  });

  it('sums late + interest, clamps clean to 0', () => {
    const res = feesByCard(
      [row('x·1', '2026-01', 'LATE PAYMENT CHARGE', 10), row('x·1', '2026-02', 'FINANCE CHARGE', 5.5)],
      ['x·1']
    );
    expect(res[0].late).toBe(10);
    expect(res[0].interest).toBe(5.5);
  });

  it('sorts actionable annual fees first', () => {
    const res = feesByCard([row('b·2', '2026-02', 'ANNUAL FEE', 250)], ['a·1', 'b·2']);
    expect(res[0].card).toBe('b·2');
  });
});
