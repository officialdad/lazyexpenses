<script lang="ts">
  import { onMount } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { app } from '$lib/data';
  import { rankCards, prettyCard, todayMYT, type CardRank } from '$lib/cardpick';
  import { bankColor, CARD_ICON } from '$lib/banks';

  let today = $state<string | null>(null);
  onMount(() => { today = todayMYT(); });

  const ranked = $derived<CardRank[]>(
    today
      ? rankCards({ cards: app.cards, cycles: app.cycles, rows: app.rows, months: app.months, today, nonSpend: app.nonSpend })
      : []
  );
  const top = $derived(ranked[0] ?? null);
  const bankOf = (c: string) => c.split('·')[0];
</script>

<div class="border p-3" style="border-color:var(--divider)">
  <h2 class="text-xs uppercase tracking-widest mb-3" style="color:var(--muted)">Use next</h2>

  {#if !today}
    <p class="text-xs" style="color:var(--muted)">…</p>
  {:else if !top}
    <p class="text-xs" style="color:var(--muted)">No card data yet.</p>
  {:else}
    <div class="flex items-center gap-3 p-3 mb-3" style="background:var(--surface)">
      <span class="shrink-0" style="color:{bankColor(bankOf(top.card))}"><Icon name={CARD_ICON} size={28} /></span>
      <div class="min-w-0">
        <b class="block text-base font-extrabold truncate" style="color:var(--text)">{prettyCard(top.card)}</b>
        <small style="color:var(--muted)">{top.why}</small>
      </div>
    </div>
    <ul class="text-sm">
      {#each ranked as c (c.card)}
        <li class="flex items-center gap-3 py-1">
          <span class="shrink-0" style="color:{bankColor(bankOf(c.card))}"><Icon name={CARD_ICON} size={18} /></span>
          <span class="flex-1 min-w-0 truncate" style="color:var(--text)">{prettyCard(c.card)}</span>
          <span class="tnum text-[12px] shrink-0" style="color:var(--muted)">{c.runwayDays}d</span>
          <span class="block w-16 h-2 shrink-0" style="background:var(--divider)">
            <span class="block h-2" style="width:{Math.round(c.share * 100)}%;background:var(--accent)"></span>
          </span>
        </li>
      {/each}
    </ul>
  {/if}
</div>
