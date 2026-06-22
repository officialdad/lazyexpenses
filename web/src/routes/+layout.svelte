<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { meta, loadAppData } from '$lib/data';
  import BottomNav from '$lib/components/BottomNav.svelte';
  import TopBar from '$lib/components/TopBar.svelte';
  import Dashboard from '$lib/components/Dashboard.svelte';
  let { children } = $props();

  // Runtime fetch — client-only (onMount never runs during prerender, so the static
  // shell ships the skeleton; data hydrates here).
  onMount(() => { loadAppData(); });
</script>
<svelte:head><meta name="theme-color" content="#000000" /></svelte:head>

{#if meta.status === 'ready'}
  <!-- Mobile + tablet (<1024px): routed, tabbed, bottom nav -->
  <!-- IMPORTANT: these two subtrees MUST use display:none toggling (lg:hidden /
       hidden lg:block Tailwind classes). Do NOT switch to visibility:hidden or
       opacity:0 — only display:none removes the inert subtree from the
       accessibility tree so screen readers see only the active layout. -->
  <div class="lg:hidden">
    <main class="mx-auto px-4 pb-24 pt-4 max-w-md md:max-w-3xl">{@render children()}</main>
    <BottomNav />
  </div>

  <!-- Desktop (>=1024px): unified dashboard, sticky top nav -->
  <div class="hidden lg:block">
    <TopBar />
    <Dashboard />
  </div>
{:else if meta.status === 'error'}
  <main class="mx-auto max-w-md px-4 py-16 text-center">
    <p class="text-base font-bold" style="color:#f87171">Couldn't load data</p>
    <p class="mt-2 text-sm" style="color:var(--muted)">{meta.error}</p>
    <button
      class="mt-4 rounded-lg px-4 py-2 text-sm font-bold"
      style="background:var(--surface);color:var(--text)"
      onclick={() => loadAppData()}
    >Retry</button>
  </main>
{:else}
  <main data-loading class="mx-auto max-w-md px-4 py-16 text-center">
    <p class="text-sm" style="color:var(--muted)">Loading…</p>
  </main>
{/if}
