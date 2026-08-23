<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { meta, loadAppData, login } from '$lib/data';
  import { paid } from '$lib/paid.svelte';
  import { waivers } from '$lib/waivers.svelte';
  import { cats } from '$lib/cats.svelte';
  import { net, initNet } from '$lib/net.svelte';
  import { initPush } from '$lib/push.svelte';
  import BottomNav from '$lib/components/BottomNav.svelte';
  import TopBar from '$lib/components/TopBar.svelte';
  import Dashboard from '$lib/components/Dashboard.svelte';
  import Toast from '$lib/components/Toast.svelte';
  import Skeleton from '$lib/components/Skeleton.svelte';
  import SyncStatus from '$lib/components/SyncStatus.svelte';
  import SearchOverlay from '$lib/components/SearchOverlay.svelte';
  import Setup from '$lib/components/Setup.svelte';
  let { children } = $props();

  // Runtime fetch — client-only (onMount never runs during prerender, so the static
  // shell ships the skeleton; data hydrates here).
  // initPush() here and not in BillsDue: both the mobile and desktop subtrees mount at
  // every width, so the panel renders twice and would probe the browser twice.
  onMount(() => { initNet(); loadAppData(); paid.load(); waivers.load(); cats.load(); initPush(); });

  // Password gate (#51): the server 401s the data routes when APP_PASSWORD is set, and
  // loadAppData turns that into meta.status === 'auth'. One form, one cookie, no route.
  // Routes the desktop Dashboard already renders as anchored sections. Anything else
  // (/settings, #40) is a plain page and is rendered once, above.
  const DASHBOARD_ROUTES = ['/', '/trends', '/cuts', '/fees'];

  let pw = $state('');
  let pwError = $state('');
  let busy = $state(false);
  async function unlock(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    pwError = '';
    const ok = await login(pw);
    busy = false;
    if (!ok) { pwError = 'Wrong password'; return; }
    pw = '';
    await loadAppData();
    paid.load();
    waivers.load();
    cats.load();
  }
</script>
<svelte:head><meta name="theme-color" content="#000000" /></svelte:head>

<!-- App-wide overlays, available in every state (loading/error/ready). -->
<Toast />
<SearchOverlay />

{#if meta.status === 'ready' && !DASHBOARD_ROUTES.includes(page.url.pathname)}
  <!-- #40: a route the Dashboard does not render as a section (/settings) mounts ONCE,
       outside the dual subtree below. Those two subtrees both mount at every width, which
       is fine for charts and fatal for a form — duplicate element ids mean every
       <label for> binds to whichever copy the browser saw first. -->
  {@render children()}
{:else if meta.status === 'ready'}
  <!-- Mobile + tablet (<1024px): routed, tabbed, bottom nav -->
  <!-- IMPORTANT: these two subtrees MUST use display:none toggling (lg:hidden /
       hidden lg:block Tailwind classes). Do NOT switch to visibility:hidden or
       opacity:0 — only display:none removes the inert subtree from the
       accessibility tree so screen readers see only the active layout. -->
  <div class="lg:hidden">
    <main class="mx-auto px-4 pb-24 pt-4 max-w-md md:max-w-3xl">
      <div class="mb-2 flex items-center justify-end gap-3">
        <!-- #66: the Settings link that used to sit here is now a BottomNav tab. -->
        <SyncStatus />
      </div>
      {@render children()}
    </main>
    <BottomNav />
  </div>

  <!-- Desktop (>=1024px): unified dashboard, sticky top nav -->
  <div class="hidden lg:block">
    <TopBar />
    <Dashboard />
  </div>
{:else if meta.status === 'auth'}
  <main class="mx-auto max-w-md px-4 py-16 text-center">
    <p class="text-base font-bold">Password required</p>
    <p class="mt-2 text-sm" style="color:var(--muted)">This app is locked. Enter the password it was set up with.</p>
    <form class="mt-4 flex flex-col gap-3" onsubmit={unlock}>
      <label class="sr-only" for="app-password">Password</label>
      <input
        id="app-password"
        type="password"
        autocomplete="current-password"
        bind:value={pw}
        class="px-3 py-2 text-sm"
        style="background:var(--surface);color:var(--text)"
      />
      <button
        type="submit"
        disabled={busy}
        class="px-4 py-2 text-sm font-bold"
        style="background:var(--surface);color:var(--text)"
      >{busy ? 'Checking…' : 'Unlock'}</button>
    </form>
    {#if pwError}<p class="mt-3 text-sm font-bold" style="color:#f87171">{pwError}</p>{/if}
  </main>
{:else if meta.status === 'setup'}
  <!-- #40: an empty volume is not an error, it is the state onboarding exists for.
       This used to be a 404 and a blank page. -->
  <Setup first={true} />
{:else if meta.status === 'error'}
  <main class="mx-auto max-w-md px-4 py-16 text-center">
    {#if !net.online}
      <p class="text-base font-bold" style="color:#f87171">You're offline</p>
      <p class="mt-2 text-sm" style="color:var(--muted)">No cached copy yet — reconnect to load your data.</p>
    {:else}
      <p class="text-base font-bold" style="color:#f87171">Couldn't load data</p>
      <p class="mt-2 text-sm" style="color:var(--muted)">{meta.error}</p>
    {/if}
    <button
      class="mt-4 px-4 py-2 text-sm font-bold"
      style="background:var(--surface);color:var(--text)"
      onclick={() => loadAppData()}
    >Retry</button>
  </main>
{:else}
  <Skeleton />
{/if}
