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
  // (/settings, #40) is a plain page the shell renders at every width.
  const DASHBOARD_ROUTES = ['/', '/trends', '/cuts', '/fees'];

  // #87: one content scale, owned by the layout rather than by each leaf. Full-bleed with
  // px-4 on a phone — a 448px cap gutters a 600px window — then a 768px cap that holds all
  // the way up, because a single-column form stretched to the desktop grid's 7xl is
  // unreadable. The desktop Dashboard keeps its own max-w-7xl: it is a multi-column grid,
  // not a column, and TopBar is sized to match it.
  const WIDTH = 'mx-auto px-4 md:max-w-3xl';

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

{#if meta.status === 'ready'}
  <!-- #86: ONE width-responsive shell — TopBar above 1024px, BottomNav below it, and
       children() rendered EXACTLY ONCE between them. /settings used to render on its own
       above a dual subtree and so had no navigation at any width; it cannot simply join
       that subtree either, because both halves mount at every width and duplicate element
       ids mean every <label for> in Setup binds to whichever copy the browser saw first.
       IMPORTANT: the width toggles MUST stay display:none (lg:hidden / hidden lg:block).
       Do NOT switch to visibility:hidden or opacity:0 — only display:none removes the
       inert subtree from the accessibility tree. -->
  <div class="hidden lg:block"><TopBar /></div>

  {#if DASHBOARD_ROUTES.includes(page.url.pathname)}
    <!-- Desktop renders all four views as anchored sections instead of the routed one, so
         this pair really does mount twice at every width. That is fine for charts (and the
         all-time aggregates are precomputed once in data.svelte.ts, so it costs no
         compute); it is only a form that cannot survive it. -->
    <main class="{WIDTH} pb-24 pt-4 lg:hidden">
      <div class="mb-2 flex items-center justify-end gap-3">
        <!-- #66: the Settings link that used to sit here is now a BottomNav tab. -->
        <SyncStatus />
      </div>
      {@render children()}
    </main>
    <div class="hidden lg:block"><Dashboard /></div>
  {:else}
    <!-- A plain page (/settings) brings its own <main>, so this wrapper is a div. -->
    <div class="{WIDTH} pb-24 lg:pb-0">{@render children()}</div>
  {/if}

  <div class="lg:hidden"><BottomNav /></div>
{:else if meta.status === 'auth'}
  <main class="{WIDTH} py-16 text-center">
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
  <main class="{WIDTH} py-16 text-center">
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
