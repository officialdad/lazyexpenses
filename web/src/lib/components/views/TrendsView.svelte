<script lang="ts">
  import MonthlyTrend from '$lib/components/charts/MonthlyTrend.svelte';
  import CategoryDonut from '$lib/components/charts/CategoryDonut.svelte';
  import TopMerchants from '$lib/components/charts/TopMerchants.svelte';
</script>

<h1 class="text-[13px] uppercase tracking-widest mb-3" style="color:var(--muted)">Trends</h1>
<div class="grid grid-cols-1 gap-4 md:grid-cols-2">
  <MonthlyTrend />
  <CategoryDonut />
  <div class="md:col-span-2"><TopMerchants /></div>
</div>
