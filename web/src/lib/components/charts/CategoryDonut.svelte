<script lang="ts">
  import { app, agg } from '$lib/data';
  import { rm, monthLabel } from '$lib/fmt';
  import { byCategory } from '$lib/trends';
  import Icon from '$lib/components/Icon.svelte';
  import { inview } from '$lib/inview';

  // null month → all-time (precomputed agg); a month → re-scope to that month.
  // `selected` (bindable) is the clicked category — owned by TrendsView so TopMerchants re-scopes to it.
  let { month = null, selected = $bindable<string | null>(null) }:
    { month?: string | null; selected?: string | null } = $props();

  const pick = (g: string) => (selected = selected === g ? null : g);
  const keyPick = (e: KeyboardEvent, g: string) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(g); }
  };

  const slices = $derived(month ? byCategory(app.rows, month, app.nonSpend) : agg.byCategory);
  const total = $derived(slices.reduce((a, s) => a + s.total, 0));

  // Compute SVG arc paths for donut chart
  function polarToXY(cx: number, cy: number, r: number, angle: number) {
    return {
      x: cx + r * Math.cos(angle - Math.PI / 2),
      y: cy + r * Math.sin(angle - Math.PI / 2)
    };
  }

  function arcPath(cx: number, cy: number, r: number, innerR: number, startAngle: number, endAngle: number) {
    const s = polarToXY(cx, cy, r, startAngle);
    const e = polarToXY(cx, cy, r, endAngle);
    const si = polarToXY(cx, cy, innerR, startAngle);
    const ei = polarToXY(cx, cy, innerR, endAngle);
    const large = endAngle - startAngle > Math.PI ? 1 : 0;
    return [
      `M ${s.x} ${s.y}`,
      `A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`,
      `L ${ei.x} ${ei.y}`,
      `A ${innerR} ${innerR} 0 ${large} 0 ${si.x} ${si.y}`,
      'Z'
    ].join(' ');
  }

  type ArcEntry = { path: string; color: string; g: string; total: number; pct: number };

  function buildArcs(slices: { g: string; total: number }[], totalVal: number): ArcEntry[] {
    const cx = 100, cy = 100, r = 80, innerR = 50;
    // Floor each present slice to ~2.3° then renormalize so the ring still closes at 360°.
    // Without this a sub-1% category (e.g. Charity/Certifications at ~1.3°) is invisible.
    // ponytail: tiny slices borrow a sliver from the large ones — sub-1% distortion; the
    // legend + aria still report the TRUE pct (s.total/totalVal), so nothing is misstated.
    const MIN = 0.04;
    const raw = slices.map(s => Math.max(totalVal > 0 ? (s.total / totalVal) * 2 * Math.PI : 0, s.total > 0 ? MIN : 0));
    const scale = (2 * Math.PI) / (raw.reduce((a, b) => a + b, 0) || 1);
    let angle = 0;
    return slices.map((s, i) => {
      const pct = totalVal > 0 ? s.total / totalVal : 0;
      const delta = raw[i] * scale;
      const p = arcPath(cx, cy, r, innerR, angle, angle + Math.max(delta - 0.01, 0));
      angle += delta;
      return { path: p, color: app.colors[s.g] ?? '#555', g: s.g, total: s.total, pct };
    });
  }

  const arcs = $derived(buildArcs(slices, total));
</script>

<div class="border p-3" style="border-color:var(--divider)" use:inview>
  <h2 class="text-xs uppercase tracking-widest mb-3" style="color:var(--muted)">
    Spend by Category{#if month}&nbsp;· {monthLabel(month)}{/if}
  </h2>
  {#if slices.length === 0}
    <p class="text-xs py-8 text-center" style="color:var(--muted)">No data</p>
  {:else}
    <div class="flex flex-col gap-4 sm:flex-row sm:items-start">
      <!-- SVG Donut — slices are clickable (mirror of the legend) to drill into a category -->
      <div class="shrink-0 mx-auto donut-sweep" style="width:200px;height:200px">
        <svg viewBox="0 0 200 200" width="200" height="200" role="img" aria-label="Category spend donut chart">
          {#each arcs as a (a.g)}
            {@const sel = a.g === selected}
            <path
              d={a.path}
              fill={a.color}
              stroke="var(--bg)"
              stroke-width="1.5"
              class="slice"
              role="button"
              tabindex="0"
              aria-pressed={sel}
              aria-label="{a.g} {rm(a.total)}, show merchants"
              style="opacity:{selected && !sel ? 0.4 : 1};cursor:pointer"
              onclick={() => pick(a.g)}
              onkeydown={(e) => keyPick(e, a.g)}
            >
              <title>{a.g}: {rm(a.total)}</title>
            </path>
          {/each}
          <!-- Center label: single total figure at 16px (no downscale → effective 16px ≥ 11px) -->
          <text x="100" y="108" text-anchor="middle" font-size="16" fill="var(--text)" font-family="inherit" font-weight="600">{rm(total)}</text>
        </svg>
      </div>
      <!-- Legend (DOM buttons — fully legible + keyboard-accessible); category icon tinted to the slice colour -->
      <ul class="flex-1 space-y-1.5 min-w-0">
        {#each arcs as a (a.g)}
          {@const sel = a.g === selected}
          <li class="min-w-0">
            <button
              type="button"
              class="legrow w-full flex items-center gap-2 text-xs min-w-0 bg-transparent border-0 p-0 text-left cursor-pointer"
              aria-pressed={sel}
              aria-label="{a.g} {rm(a.total)}, show merchants"
              onclick={() => pick(a.g)}
            >
              <span class="shrink-0 inline-flex" style="color:{a.color}">
                <Icon name={app.catIcon[a.g] ?? 'shape-outline'} size={14} />
              </span>
              <span class="truncate" title={a.g} style="color:{sel ? 'var(--accent)' : 'var(--text)'};font-weight:{sel ? 600 : 400}">{a.g}</span>
              <span class="ml-auto tabular-nums shrink-0 pl-2" style="color:var(--muted)">{rm(a.total)}</span>
            </button>
          </li>
        {/each}
      </ul>
    </div>
    {#if selected}
      <div class="mt-3 pt-3 border-t flex" style="border-color:var(--divider)">
        <button type="button" class="back text-[11px] ml-auto underline cursor-pointer bg-transparent border-0 p-0" style="color:var(--accent)" onclick={() => (selected = null)}>
          ← Show all categories
        </button>
      </div>
    {/if}
  {/if}
</div>

<style>
  .slice:focus-visible { outline: 2px solid var(--text); outline-offset: 1px; }
  .legrow:focus-visible, .back:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
</style>
