<script lang="ts">
  import MonthlyTrend from '$lib/components/charts/MonthlyTrend.svelte';
  import CategoryDonut from '$lib/components/charts/CategoryDonut.svelte';
  import TopMerchants from '$lib/components/charts/TopMerchants.svelte';

  // Clicking a bar in MonthlyTrend sets this; the donut + merchants re-scope to it (null = all months).
  let selectedMonth = $state<string | null>(null);
</script>

<h1 class="text-[13px] uppercase tracking-widest mb-3" style="color:var(--muted)">Trends</h1>
<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
  <MonthlyTrend bind:selected={selectedMonth} />
  <CategoryDonut month={selectedMonth} />
  <div class="md:col-span-2"><TopMerchants month={selectedMonth} /></div>
</div>
