<script lang="ts">
  import '../app.css';
  import BottomNav from '$lib/components/BottomNav.svelte';
  let { children } = $props();
</script>
<svelte:head><meta name="theme-color" content="#000000" /></svelte:head>
<main class="max-w-md mx-auto px-4 pb-24 pt-4">{@render children()}</main>
<BottomNav />
