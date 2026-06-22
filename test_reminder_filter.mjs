// Run: node test_reminder_filter.mjs   (prints "REMINDER FILTER OK" or throws)
import { billsDueIn } from './n8n-reminder-filter.mjs';
import assert from 'node:assert';

const bills = [
  { bank: 'cimb', payment_due_date: '2026-07-05', current_balance: 1234 },
  { bank: 'maybank', payment_due_date: '2026-07-04', current_balance: 50 },
  { bank: 'sc', payment_due_date: '2026-07-06', current_balance: 99 },
  { bank: 'rhb', payment_due_date: null, current_balance: 10 },
];

// today = 2026-07-02 -> due in 3 days == 2026-07-05 -> only cimb
const hit = billsDueIn(bills, '2026-07-02', 3);
assert.strictEqual(hit.length, 1, `expected 1 got ${hit.length}`);
assert.strictEqual(hit[0].bank, 'cimb');

// boundary: 2 days out (07-04) excluded, 4 days out (07-06) excluded
assert.strictEqual(billsDueIn(bills, '2026-07-02', 2).length, 1); // maybank only
assert.strictEqual(billsDueIn(bills, '2026-07-02', 2)[0].bank, 'maybank');
assert.strictEqual(billsDueIn(bills, '2026-07-02', 4)[0].bank, 'sc');

// null due dates never match
assert.ok(billsDueIn(bills, '2026-07-02', 3).every((b) => b.payment_due_date));

// month boundary: today 2026-07-30, +3 -> 2026-08-02
const aug = [{ bank: 'x', payment_due_date: '2026-08-02' }];
assert.strictEqual(billsDueIn(aug, '2026-07-30', 3).length, 1);

console.log('REMINDER FILTER OK');
