<script lang="ts">
  import { monthlyAll } from '$lib/data';
  import { rm, kRM } from '$lib/fmt';

  const series = monthlyAll;
  const max = Math.max(...series.map((s) => s.total), 1);

  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function fmtMonth(m: string) {
    const [yr, mo] = m.split('-');
    return (monthNames[parseInt(mo, 10) - 1] ?? m) + " '" + (yr?.slice(2) ?? '');
  }
</script>

<div class="border p-3" style="border-color:var(--divider)">
  <h2 class="text-xs uppercase tracking-widest mb-3" style="color:var(--muted)">Monthly Spend</h2>
  {#if series.length === 0}
    <p class="text-xs py-8 text-center" style="color:var(--muted)">No data</p>
  {:else}
    <div class="flex items-end gap-1 overflow-x-auto pb-1 px-0.5" style="min-height:160px">
      {#each series as s}
        {@const pct = max > 0 ? (s.total / max) * 140 : 0}
        <div class="flex flex-col items-center shrink-0" style="min-width:36px;flex:1">
          <span class="text-[12px] mb-1 tabular-nums text-center leading-tight" style="color:var(--muted)" title={rm(s.total)}>
            {kRM(s.total)}
          </span>
          <div
            class="w-full"
            style="height:{Math.max(pct, 2)}px; background:var(--accent); min-width:8px"
            title="{fmtMonth(s.month)}: {rm(s.total)}"
          ></div>
          <span class="text-[12px] mt-1 text-center leading-tight" style="color:var(--muted); max-width:40px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">
            {fmtMonth(s.month)}
          </span>
        </div>
      {/each}
    </div>
  {/if}
</div>
