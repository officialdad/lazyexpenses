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

  const LABEL: Record<WaiverStatus, string> = { tocall: 'To call', requested: 'Requested', waived: 'Waived' };
  const GLYPH: Record<WaiverStatus, string> = { tocall: '●', requested: '◐', waived: '✓' };
  // small-text tokens (vetted for AA contrast in the dashboard a11y pass)
  const COLOR: Record<WaiverStatus, string> = { tocall: '#f87171', requested: 'var(--muted)', waived: '#34d399' };
</script>

<section aria-label="Fees and waivers" class="border p-3" style="border-color:var(--divider)">
  <h2 class="text-xs uppercase tracking-widest mb-1" style="color:var(--muted)">Fees &amp; waivers</h2>
  <p class="text-[11px] mb-3" style="color:var(--muted)">
    Annual fees that need a waiver call, plus any late-payment or interest charge per card.
  </p>

  {#if !cards.length}
    <p class="text-xs" style="color:var(--muted)">No card data yet.</p>
  {:else}
    <ul class="text-sm">
      {#each cards as cf (cf.card)}
        <li class="flex items-center gap-3 py-2 border-b" style="border-color:var(--divider)">
          <span class="shrink-0" style="color:{bankColor(bankOf(cf.card))}"><Icon name={CARD_ICON} size={20} /></span>

          <div class="flex-1 min-w-0">
            <div class="truncate font-bold" style="color:var(--text)">{prettyCard(cf.card)}</div>
            <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] tnum mt-0.5">
              <span style="color:{cf.late > 0 ? '#f87171' : '#34d399'}">Late {rm(cf.late, true)}</span>
              <span style="color:{cf.interest > 0 ? '#f87171' : '#34d399'}">Interest {rm(cf.interest, true)}</span>
            </div>
          </div>

          <div class="shrink-0 text-right">
            {#if cf.annual && !cf.annual.reversed}
              {@const af = cf.annual}
              {@const st = waivers.status(af.key)}
              <div class="tnum font-bold" style="color:var(--text)">{rm(af.amount, true)}</div>
              <button
                type="button"
                class="feebtn text-[11px] cursor-pointer bg-transparent border-0 p-0 mt-0.5"
                style="color:{COLOR[st]}"
                aria-label="Annual fee {rm(af.amount, true)} for {prettyCard(cf.card)}, {monthLabel(af.month)} — {LABEL[st]}; tap to mark {LABEL[nextStatus(st)]}"
                onclick={() => waivers.set(af.key, nextStatus(st))}
              >
                {GLYPH[st]} {LABEL[st]}
              </button>
            {:else if cf.annual}
              <div class="tnum" style="color:var(--muted);text-decoration:line-through">{rm(cf.annual.amount, true)}</div>
              <div class="text-[11px]" style="color:#34d399">✓ reversed</div>
            {:else}
              <div class="text-[12px]" style="color:var(--muted)">—</div>
              <div class="text-[11px]" style="color:#34d399">no annual fee</div>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .feebtn:focus-visible {
    outline: 2px solid var(--text);
    outline-offset: 2px;
  }
</style>
