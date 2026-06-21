<script lang="ts">
  import MonthlyTrend from '$lib/components/charts/MonthlyTrend.svelte';
  import CategoryDonut from '$lib/components/charts/CategoryDonut.svelte';
  import TopMerchants from '$lib/components/charts/TopMerchants.svelte';
</script>

<h1 class="text-[10px] uppercase tracking-widest mb-3" style="color:var(--muted)">Trends</h1>
<MonthlyTrend />
<CategoryDonut />
<TopMerchants />
