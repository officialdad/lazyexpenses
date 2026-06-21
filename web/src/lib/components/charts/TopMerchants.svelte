<script lang="ts">
  import { app } from '$lib/data';
  import { rm } from '$lib/fmt';
  import { topMerchants } from '$lib/trends';

  const merchants = $derived(topMerchants(app.rows, 20, app.nonSpend));
  const max = $derived(Math.max(...merchants.map(m => m.total), 1));

  // Clamp long merchant names
  function clamp(s: string, n = 28) {
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }
</script>

<div class="border p-3 mb-4" style="border-color:var(--divider)">
  <h2 class="text-xs uppercase tracking-widest mb-3" style="color:var(--muted)">Top 20 Merchants</h2>
  {#if merchants.length === 0}
    <p class="text-xs py-8 text-center" style="color:var(--muted)">No data</p>
  {:else}
    <div class="space-y-1.5">
      {#each merchants as m, i}
        {@const barPct = max > 0 ? (m.total / max) * 100 : 0}
        <div class="flex items-center gap-2 text-xs">
          <!-- Rank -->
          <span class="tabular-nums shrink-0 w-5 text-right" style="color:var(--muted)">{i + 1}</span>
          <!-- Merchant name + bar -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-0.5">
              <span class="truncate" title={m.d}>{clamp(m.d)}</span>
              <span class="ml-auto tabular-nums shrink-0 pl-2" style="color:var(--text)">{rm(m.total)}</span>
            </div>
            <div class="h-1.5 w-full" style="background:var(--divider)">
              <div
                class="h-full"
                style="width:{barPct}%;background:var(--accent)"
              ></div>
            </div>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
