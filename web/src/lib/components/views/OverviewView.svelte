<script lang="ts">
  import { app, latestMonth } from '$lib/data';
  import HeadroomHero from '$lib/components/HeadroomHero.svelte';
  import KpiChips from '$lib/components/KpiChips.svelte';
  import CardPick from '$lib/components/CardPick.svelte';
  import BillsDue from '$lib/components/BillsDue.svelte';

  let { month = latestMonth() }: { month?: string } = $props();
</script>

<header
  class="flex justify-between items-center text-[13px] uppercase tracking-wide font-bold mb-3"
  style="color:var(--muted)"
>
  <span>{month}</span>
  <span>{app.range}</span>
</header>

<div class="lg:grid lg:grid-cols-2 lg:gap-6 lg:items-start">
  <HeadroomHero {month} />
  <KpiChips {month} />
</div>

<CardPick />
<BillsDue />
