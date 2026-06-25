<script lang="ts">
  import { agg } from '$lib/data';
  import { rm, pct, kRM, moName, yr2, monthLabel } from '$lib/fmt';
  import { monthDelta } from '$lib/trends';
  import { inview } from '$lib/inview';

  // Selected month is owned by the parent (TrendsView) so the donut + merchants re-scope to it.
  let { selected = $bindable<string | null>(null) }: { selected?: string | null } = $props();

  const series = agg.monthly;
  const max = Math.max(...series.map((s) => s.total), 1);

  // year label only on the first bar of each year (and the very first bar) — ponytail: avoids repeating the year on every bar
  const showYear = (i: number) => i === 0 || series[i].month.slice(0, 4) !== series[i - 1].month.slice(0, 4);
  const pick = (m: string) => (selected = selected === m ? null : m);

  const caption = $derived.by(() => {
    if (!selected) return null;
    return {
      total: series.find((s) => s.month === selected)?.total ?? 0,
      delta: monthDelta(series, selected)
    };
  });
</script>

<div class="border p-3" style="border-color:var(--divider)" use:inview>
  <h2 class="text-xs uppercase tracking-widest mb-3" style="color:var(--muted)">Monthly Spend</h2>
  {#if series.length === 0}
    <p class="text-xs py-8 text-center" style="color:var(--muted)">No data</p>
  {:else}
    <div class="flex items-end gap-1 overflow-x-auto scroll-thin pb-1 px-0.5" style="min-height:170px">
      {#each series as s, i (s.month)}
        {@const h = max > 0 ? (s.total / max) * 140 : 0}
        {@const sel = selected === s.month}
        <button
          type="button"
          class="bar flex flex-col items-center shrink-0 bg-transparent border-0 p-0 cursor-pointer"
          style="min-width:26px;flex:1"
          aria-pressed={sel}
          aria-label="{monthLabel(s.month)} {rm(s.total)}, show this month's breakdown"
          onclick={() => pick(s.month)}
        >
          <span class="text-[12px] mb-1 tabular-nums text-center leading-tight" style="color:{sel ? 'var(--text)' : 'var(--muted)'}">
            {kRM(s.total)}
          </span>
          <div
            class="w-full grow-y"
            style="height:{Math.max(h, 2)}px; background:var(--accent); min-width:8px; opacity:{selected && !sel ? 0.4 : 1}; animation-delay:{i * 45}ms"
            title="{monthLabel(s.month)}: {rm(s.total)}"
          ></div>
          <span class="text-[12px] mt-1 leading-tight" style="color:{sel ? 'var(--accent)' : 'var(--muted)'}; font-weight:{sel ? 600 : 400}">{moName(s.month)}</span>
          <span class="text-[11px] tabular-nums leading-tight" style="color:var(--muted);height:13px">{showYear(i) ? yr2(s.month) : ''}</span>
        </button>
      {/each}
    </div>

    {#if selected && caption}
      <div class="mt-3 pt-3 border-t flex items-baseline gap-2 flex-wrap" style="border-color:var(--divider)">
        <span class="text-sm font-semibold" style="color:var(--text)">{monthLabel(selected)}</span>
        <span class="text-sm tabular-nums" style="color:var(--text)">{rm(caption.total)}</span>
        {#if caption.delta}
          {@const up = caption.delta.abs > 0}
          <span class="text-[11px] tabular-nums" style="color:{up ? '#f87171' : '#34d399'}">
            {up ? '▲' : '▼'} {rm(Math.abs(caption.delta.abs))} ({pct(Math.abs(caption.delta.pct))}) vs prev
          </span>
        {/if}
        <button type="button" class="back text-[11px] ml-auto underline cursor-pointer bg-transparent border-0 p-0" style="color:var(--accent)" onclick={() => (selected = null)}>
          ← Show all months
        </button>
      </div>
    {/if}
  {/if}
</div>

<style>
  /* native thin always-visible scrollbar — no lib */
  .scroll-thin { scrollbar-width: thin; scrollbar-color: var(--muted) transparent; }
  .scroll-thin::-webkit-scrollbar { height: 6px; }
  .scroll-thin::-webkit-scrollbar-thumb { background: var(--muted); border-radius: 3px; }
  .scroll-thin::-webkit-scrollbar-track { background: transparent; }
  .bar:focus-visible, .back:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
</style>
