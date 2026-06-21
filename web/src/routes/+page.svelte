<script lang="ts">
  import { app, latestMonth } from '$lib/data';
  import HeadroomHero from '$lib/components/HeadroomHero.svelte';
  import KpiChips from '$lib/components/KpiChips.svelte';

  let month = $state(latestMonth);
</script>

<header
  class="flex justify-between items-center text-[13px] uppercase tracking-wide font-bold mb-3"
  style="color:var(--muted)"
>
  <span>{month}</span>
  <span>{app.range}</span>
</header>

<HeadroomHero {month} />
<KpiChips {month} />
