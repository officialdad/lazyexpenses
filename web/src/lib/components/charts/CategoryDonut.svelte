<script lang="ts">
  import { app } from '$lib/data';
  import { rm } from '$lib/fmt';
  import { byCategory } from '$lib/trends';

  const slices = $derived(byCategory(app.rows, null, app.nonSpend));
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
    let angle = 0;
    return slices.map(s => {
      const pct = totalVal > 0 ? s.total / totalVal : 0;
      const delta = pct * 2 * Math.PI;
      const p = arcPath(cx, cy, r, innerR, angle, angle + Math.max(delta - 0.01, 0));
      angle += delta;
      return { path: p, color: app.colors[s.g] ?? '#555', g: s.g, total: s.total, pct };
    });
  }

  const arcs = $derived(buildArcs(slices, total));

  // Clamp long names for legend
  function clamp(s: string, n = 22) {
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }
</script>

<div class="border p-3 mb-4" style="border-color:var(--divider)">
  <h2 class="text-xs uppercase tracking-widest mb-3" style="color:var(--muted)">Spend by Category</h2>
  {#if slices.length === 0}
    <p class="text-xs py-8 text-center" style="color:var(--muted)">No data</p>
  {:else}
    <div class="flex flex-col gap-4 sm:flex-row sm:items-start">
      <!-- SVG Donut -->
      <div class="shrink-0 mx-auto" style="width:200px;height:200px">
        <svg viewBox="0 0 200 200" width="200" height="200" role="img" aria-label="Category spend donut chart">
          {#each arcs as a}
            <path d={a.path} fill={a.color} stroke="var(--bg)" stroke-width="1.5">
              <title>{a.g}: {rm(a.total)}</title>
            </path>
          {/each}
          <!-- Center label: single total figure at 16px (no downscale → effective 16px ≥ 11px) -->
          <text x="100" y="108" text-anchor="middle" font-size="16" fill="var(--text)" font-family="inherit" font-weight="600">{rm(total)}</text>
        </svg>
      </div>
      <!-- Legend (DOM text — fully legible, no SVG text) -->
      <ul class="flex-1 space-y-1.5 min-w-0">
        {#each arcs as a}
          <li class="flex items-center gap-2 text-xs min-w-0">
            <span class="inline-block shrink-0 w-2.5 h-2.5" style="background:{a.color}"></span>
            <span class="truncate" title={a.g}>{clamp(a.g)}</span>
            <span class="ml-auto tabular-nums shrink-0 pl-2" style="color:var(--muted)">{rm(a.total)}</span>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</div>
