<script lang="ts">
  import Icon from '$lib/components/Icon.svelte';
  import { app } from '$lib/data';
  import { sortBills } from '$lib/bills';
  import { prettyCard, todayMYT } from '$lib/cardpick';
  import { bankColor, CARD_ICON } from '$lib/banks';
  import { paid } from '$lib/paid.svelte';
  import { rm } from '$lib/fmt';
  import type { Bill } from '$lib/types';

  let { bills = app.bills, today = todayMYT() }: { bills?: Bill[]; today?: string } = $props();
  const rows = $derived(sortBills(bills, today, paid.keys));
</script>

<div class="border p-3" style="border-color:var(--divider)">
  <h2 class="text-xs uppercase tracking-widest mb-3" style="color:var(--muted)">Bills due</h2>
  {#if !rows.length}
    <p class="text-xs" style="color:var(--muted)">No bills yet.</p>
  {:else}
    <ul class="text-sm">
      {#each rows as b (b.bank)}
        {@const over = b.days != null && b.days < 0}
        <li
          class="flex items-center gap-3 py-2 border-b"
          style="border-color:var(--divider); opacity:{b.paid ? 0.45 : 1}"
        >
          <span class="shrink-0" style="color:{bankColor(b.bank)}"><Icon name={CARD_ICON} size={20} /></span>

          <div class="flex-1 min-w-0">
            <div class="truncate font-bold" style="color:var(--text)">{prettyCard(b.bank)}</div>
            <div
              class="flex items-center gap-1 text-[12px] tnum"
              style="color:{over || b.urgent ? '#f87171' : 'var(--muted)'}"
              data-urgent={b.urgent}
            >
              {#if over}
                <span class="inline-flex" style="color:#f87171"><Icon name="alert-circle" size={13} /></span>Overdue
              {:else if b.days === 0}
                due today
              {:else if b.payment_due_date}
                {b.payment_due_date}{#if b.days != null} · {b.days}d{/if}
              {:else}
                no due date
              {/if}
            </div>
          </div>

          <div class="shrink-0 text-right">
            <div class="tnum" style="color:var(--text);{b.paid ? 'text-decoration:line-through' : ''}">
              {b.current_balance == null ? '—' : rm(b.current_balance, true)}
            </div>
            {#if b.minimum_payment != null}
              <div class="tnum text-[11px]" style="color:var(--muted)">min {rm(b.minimum_payment, true)}</div>
            {/if}
          </div>

          <button
            type="button"
            class="paidbtn shrink-0 text-[11px] underline cursor-pointer bg-transparent border-0 p-0"
            style="color:{b.paid ? 'var(--muted)' : 'var(--accent)'}"
            aria-pressed={b.paid}
            aria-label="{b.paid ? 'Mark unpaid' : 'Mark paid'}: {prettyCard(b.bank)}"
            onclick={() => paid.toggle(b.bank, b.statement_month)}
          >
            {b.paid ? '✓ Paid' : 'Mark paid'}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .paidbtn:focus-visible {
    outline: 2px solid var(--text);
    outline-offset: 2px;
  }
</style>
