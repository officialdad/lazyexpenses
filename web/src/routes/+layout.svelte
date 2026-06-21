<script lang="ts">
  import '../app.css';
  import BottomNav from '$lib/components/BottomNav.svelte';
  import TopBar from '$lib/components/TopBar.svelte';
  import Dashboard from '$lib/components/Dashboard.svelte';
  let { children } = $props();
</script>
<svelte:head><meta name="theme-color" content="#000000" /></svelte:head>

<!-- Mobile + tablet (<1024px): routed, tabbed, bottom nav -->
<div class="lg:hidden">
  <main class="mx-auto px-4 pb-24 pt-4 max-w-md md:max-w-3xl">{@render children()}</main>
  <BottomNav />
</div>

<!-- Desktop (>=1024px): unified dashboard, sticky top nav -->
<div class="hidden lg:block">
  <TopBar />
  <Dashboard />
</div>
