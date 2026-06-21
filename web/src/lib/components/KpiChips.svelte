<script lang="ts">
  import { app } from '$lib/data';
  import { cashbackFor, discretionaryTotal, prevMonth } from '$lib/spend';
  import { rm } from '$lib/fmt';

  let { month }: { month: string } = $props();

  const cashback = $derived(cashbackFor(app.rows, month));
  const committedMonthly = $derived(app.committed.monthly);
  const prev = $derived(prevMonth(app.months, month));
  const cur = $derived(discretionaryTotal(app.rows, month, app.nonSpend));
  const delta = $derived(prev ? cur - discretionaryTotal(app.rows, prev, app.nonSpend) : 0);
</script>

<div class="flex border-y mt-4 text-center" style="border-color:var(--divider)" aria-label="Key figures">
  <div class="flex-1 py-2 border-r" style="border-color:var(--divider)">
    <b class="block text-base font-extrabold tnum" style="color:var(--ok)">{rm(cashback)}</b>
    <small class="text-[12px] uppercase font-bold" style="color:var(--muted)">cashback</small>
  </div>
  <div class="flex-1 py-2 border-r" style="border-color:var(--divider)">
    <b class="block text-base font-extrabold tnum">{rm(committedMonthly)}</b>
    <small class="text-[12px] uppercase font-bold" style="color:var(--muted)">committed/mo</small>
  </div>
  <div class="flex-1 py-2">
    <b
      class="block text-base font-extrabold tnum"
      style="color:{delta > 0 ? 'var(--over)' : 'var(--ok)'}"
    >{delta > 0 ? '+' : ''}{rm(delta)}</b>
    <small class="text-[12px] uppercase font-bold" style="color:var(--muted)">vs {prev ?? '—'}</small>
  </div>
</div>
