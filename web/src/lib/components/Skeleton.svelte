<!-- Loading placeholder shaped like the home view (hero + KPI chips + bill rows).
     animate-pulse is disabled under prefers-reduced-motion by the global rule in app.css. -->
<div
  class="mx-auto max-w-md px-4 pb-24 pt-4 animate-pulse"
  data-loading
  role="status"
  aria-busy="true"
>
  <span class="sr-only">Loading your data…</span>
  <div class="h-28 border" style="border-color:var(--divider);background:var(--surface)" aria-hidden="true"></div>
  <div class="mt-3 flex gap-2" aria-hidden="true">
    <div class="h-14 flex-1 border" style="border-color:var(--divider);background:var(--surface)"></div>
    <div class="h-14 flex-1 border" style="border-color:var(--divider);background:var(--surface)"></div>
    <div class="h-14 flex-1 border" style="border-color:var(--divider);background:var(--surface)"></div>
  </div>
  <div class="mt-3 h-40 border" style="border-color:var(--divider);background:var(--surface)" aria-hidden="true"></div>
  <div class="mt-3 space-y-2 border p-3" style="border-color:var(--divider)" aria-hidden="true">
    <div class="h-8" style="background:var(--surface2)"></div>
    <div class="h-8" style="background:var(--surface2)"></div>
    <div class="h-8" style="background:var(--surface2)"></div>
  </div>
</div>
