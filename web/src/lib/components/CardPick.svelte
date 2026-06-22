<script lang="ts">
  import { onMount } from 'svelte';
  import { app } from '$lib/data';
  import { rankCards, prettyCard, todayMYT, type CardRank } from '$lib/cardpick';

  let today = $state<string | null>(null);
  onMount(() => { today = todayMYT(); });

  const ranked = $derived<CardRank[]>(
    today
      ? rankCards({ cards: app.cards, cycles: app.cycles, rows: app.rows, months: app.months, today, nonSpend: app.nonSpend })
      : []
  );
  const top = $derived(ranked[0] ?? null);
</script>

<section class="mt-6" aria-label="Which card to use next">
  <h2 class="text-[13px] uppercase tracking-wide font-bold mb-2" style="color:var(--muted)">Use next</h2>

  {#if !today}
    <p class="text-sm" style="color:var(--muted)">…</p>
  {:else if !top}
    <p class="text-sm" style="color:var(--muted)">No card data yet.</p>
  {:else}
    <div class="rounded-lg p-3 mb-3" style="background:var(--surface)">
      <b class="block text-base font-extrabold" style="color:var(--text)">{prettyCard(top.card)}</b>
      <small style="color:var(--muted)">{top.why}</small>
    </div>
    <ul class="text-sm">
      {#each ranked as c (c.card)}
        <li class="flex items-center gap-3 py-1">
          <span class="flex-1 min-w-0 truncate" style="color:var(--text)">{prettyCard(c.card)}</span>
          <span class="tnum text-[12px] shrink-0" style="color:var(--muted)">{c.runwayDays}d</span>
          <span class="block w-16 h-2 rounded shrink-0" style="background:var(--divider)">
            <span class="block h-2 rounded" style="width:{Math.round(c.share * 100)}%;background:var(--accent)"></span>
          </span>
        </li>
      {/each}
    </ul>
  {/if}
</section>
