<script lang="ts">
  import { app, agg } from '$lib/data';
  import { rm, monthLabel } from '$lib/fmt';
  import { topMerchants } from '$lib/trends';
  import { inview } from '$lib/inview';

  // null month → all-time; a month and/or category → re-scope. `topMerchants` already
  // takes pre-filtered rows + an arbitrary count, so no new trends.ts function is needed.
  let { month = null, category = null }:
    { month?: string | null; category?: string | null } = $props();
  let showAll = $state(false);
  let fullNames = $state(false);

  const scoped = $derived(
    app.rows.filter((r) => (!month || r.m === month) && (!category || r.g === category))
  );
  const merchants = $derived(
    !month && !category && !showAll
      ? agg.topMerchants // fast path: precomputed all-time top 20
      : topMerchants(scoped, showAll ? scoped.length : 20, app.nonSpend)
  );
  const max = $derived(Math.max(...merchants.map((m) => m.total), 1));
  // distinct spending merchants in scope — for the "Show all (N)" label
  const totalCount = $derived(
    new Set(scoped.filter((r) => !app.nonSpend.includes(r.g)).map((r) => r.d)).size
  );
</script>

<div class="border p-3" style="border-color:var(--divider)" use:inview>
  <div class="flex flex-wrap items-center gap-2 mb-3">
    <h2 class="text-xs uppercase tracking-widest" style="color:var(--muted)">
      {#if showAll}Merchants{:else}Top 20 Merchants{/if}{#if month}&nbsp;· {monthLabel(month)}{/if}{#if category}&nbsp;· {category}{/if}
    </h2>
    <div class="ml-auto flex flex-wrap items-center gap-1.5">
      <button type="button" class="chip" aria-pressed={showAll} onclick={() => (showAll = !showAll)}>
        {showAll ? 'Top 20' : `Show all (${totalCount})`}
      </button>
      <button type="button" class="chip" aria-pressed={fullNames} onclick={() => (fullNames = !fullNames)}>
        Full names
      </button>
    </div>
  </div>
  {#if merchants.length === 0}
    <p class="text-xs py-8 text-center" style="color:var(--muted)">No data</p>
  {:else}
    <div class="space-y-1.5">
      {#each merchants as m, i (m.d)}
        {@const barPct = max > 0 ? (m.total / max) * 100 : 0}
        <div class="flex items-start gap-2 text-xs">
          <!-- Rank -->
          <span class="tabular-nums shrink-0 w-5 text-right" style="color:var(--muted)">{i + 1}</span>
          <!-- Merchant name + bar -->
          <div class="flex-1 min-w-0">
            <div class="flex items-start gap-2 mb-0.5">
              <span class="min-w-0 {fullNames ? 'break-words' : 'truncate'}" title={m.d}>{m.d}</span>
              <span class="ml-auto tabular-nums shrink-0 pl-2" style="color:var(--text)">{rm(m.total)}</span>
            </div>
            <div class="h-1.5 w-full" style="background:var(--divider)">
              <div
                class="h-full grow-x"
                style="width:{barPct}%;background:var(--accent);animation-delay:{i * 45}ms"
              ></div>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .chip {
    font-size: 11px;
    line-height: 1.4;
    padding: 1px 7px;
    border: 1px solid var(--divider2);
    color: var(--muted);
    background: transparent;
    cursor: pointer;
  }
  .chip[aria-pressed='true'] { color: var(--accent); border-color: var(--accent); }
  .chip:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
</style>
