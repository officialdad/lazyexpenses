<script lang="ts">
  import Icon from '$lib/components/Icon.svelte';
  import { app } from '$lib/data';
  import { feesByCard } from '$lib/fees';
  import { prettyCard } from '$lib/cardpick';
  import { bankColor, CARD_ICON } from '$lib/banks';
  import { waivers, nextStatus, type WaiverStatus } from '$lib/waivers.svelte';
  import { rm, monthLabel } from '$lib/fmt';

  const cards = $derived(feesByCard(app.rows, app.cards));
  const bankOf = (c: string) => c.split('·')[0];

  // small-text tokens vetted for AA contrast in the dashboard a11y pass
  const RED = '#f87171';
  const GREEN = '#34d399';

  const ACT: Record<WaiverStatus, { label: string; color: string; icon: string }> = {
    tocall: { label: 'Call to waive', color: 'var(--accent)', icon: 'phone' },
    requested: { label: 'Requested', color: 'var(--muted)', icon: '' },
    waived: { label: 'Marked waived', color: GREEN, icon: '' }
  };
  const GLYPH: Record<WaiverStatus, string> = { tocall: '', requested: '◐', waived: '✓' };
</script>

<section aria-label="Fees and waivers" class="border p-3" style="border-color:var(--divider)">
  <h2 class="flex items-center gap-2 text-xs uppercase tracking-widest mb-1" style="color:var(--muted)">
    <Icon name="receipt-text-outline" size={15} /> Fees &amp; waivers
  </h2>
  <p class="text-[11px] mb-3" style="color:var(--muted)">
    Annual fees you may need to call the bank to waive, and a per-card check for any late-payment or interest charge.
  </p>

  {#if !cards.length}
    <p class="text-xs" style="color:var(--muted)">No card data yet.</p>
  {:else}
    <ul class="text-sm">
      {#each cards as cf (cf.card)}
        <li class="flex items-center gap-3 py-2.5 border-b" style="border-color:var(--divider)">
          <span class="shrink-0" style="color:{bankColor(bankOf(cf.card))}"><Icon name={CARD_ICON} size={20} /></span>

          <div class="flex-1 min-w-0">
            <div class="truncate font-bold" style="color:var(--text)">{prettyCard(cf.card)}</div>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] tnum mt-1">
              <span class="inline-flex items-center gap-1" style="color:{cf.late > 0 ? RED : GREEN}">
                <Icon name="calendar-clock" size={13} />{cf.late > 0 ? `Late fee ${rm(cf.late, true)}` : 'No late fee'}
              </span>
              <span class="inline-flex items-center gap-1" style="color:{cf.interest > 0 ? RED : GREEN}">
                <Icon name="percent" size={13} />{cf.interest > 0 ? `Interest ${rm(cf.interest, true)}` : 'No interest'}
              </span>
            </div>
          </div>

          <div class="shrink-0 text-right">
            {#if cf.annual && !cf.annual.waived}
              {@const af = cf.annual}
              {@const st = waivers.status(af.key)}
              {@const a = ACT[st]}
              <div class="text-[11px]" style="color:var(--muted)">Annual fee</div>
              <div class="tnum font-bold mb-1" style="color:var(--text)">{rm(af.amount, true)}</div>
              <button
                type="button"
                class="feebtn"
                style="color:{a.color}"
                aria-label="Annual fee {rm(af.amount, true)} for {prettyCard(cf.card)}, {monthLabel(af.month)} — {a.label}; tap to mark {ACT[nextStatus(st)].label}"
                onclick={() => waivers.set(af.key, nextStatus(st))}
              >
                {#if a.icon}<Icon name={a.icon} size={13} />{:else}<span aria-hidden="true">{GLYPH[st]}</span>{/if}
                {a.label}
              </button>
            {:else if cf.annual}
              <div class="text-[11px]" style="color:var(--muted)">Annual fee</div>
              <div class="tnum" style="color:var(--muted);text-decoration:line-through">{rm(cf.annual.amount, true)}</div>
              <div class="inline-flex items-center gap-1 text-[11px] mt-0.5" style="color:{GREEN}">
                <span aria-hidden="true">✓</span> Waived
              </div>
            {:else}
              <div class="text-[11px]" style="color:var(--muted)">Annual fee</div>
              <div class="text-[12px]" style="color:var(--muted)">None on record</div>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .feebtn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: 1px solid currentColor;
    padding: 3px 9px;
    font-size: 11px;
    font-weight: 700;
    background: transparent;
    cursor: pointer;
  }
  .feebtn:hover {
    background: color-mix(in srgb, currentColor 12%, transparent);
  }
  .feebtn:focus-visible {
    outline: 2px solid var(--text);
    outline-offset: 2px;
  }
</style>
