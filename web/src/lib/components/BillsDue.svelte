<script lang="ts">
  import { app } from '$lib/data';
  import { sortBills } from '$lib/bills';
  import { prettyCard, todayMYT } from '$lib/cardpick';
  import { rm } from '$lib/fmt';
  import type { Bill } from '$lib/types';

  let { bills = app.bills, today = todayMYT() }: { bills?: Bill[]; today?: string } = $props();
  const rows = $derived(sortBills(bills, today));
</script>

<section class="mt-6" aria-label="Bills due">
  <h2 class="text-[13px] uppercase tracking-wide font-bold mb-2" style="color:var(--muted)">Bills due</h2>
  {#if !rows.length}
    <p class="text-sm" style="color:var(--muted)">No bills yet.</p>
  {:else}
    <ul class="text-sm">
      {#each rows as b (b.bank)}
        <li class="flex items-center gap-3 py-2 border-b" style="border-color:var(--divider)">
          <span class="flex-1 min-w-0 truncate font-bold" style="color:var(--text)">{prettyCard(b.bank)}</span>
          <span class="shrink-0 text-right">
            <span class="tnum block" style="color:var(--text)">
              {b.current_balance == null ? '—' : rm(b.current_balance)}
            </span>
            {#if b.minimum_payment != null}
              <small class="tnum block text-[12px]" style="color:var(--muted)">min {rm(b.minimum_payment)}</small>
            {/if}
          </span>
          <span
            class="tnum text-[12px] shrink-0 w-24 text-right"
            style="color:{b.urgent ? '#f87171' : 'var(--muted)'}"
            data-urgent={b.urgent}
          >
            {#if b.payment_due_date}
              {b.payment_due_date}{#if b.days != null} · {b.days < 0 ? 'overdue' : b.days + 'd'}{/if}
            {:else}
              no due date
            {/if}
          </span>
        </li>
      {/each}
    </ul>
  {/if}
</section>
