<script lang="ts">
  import { base } from '$app/paths';
  import { meta, loadAppData } from '$lib/data';
  import { paid } from '$lib/paid.svelte';
  import { net } from '$lib/net.svelte';
  import { ago } from '$lib/fmt';
  import { toast } from '$lib/toast.svelte';
  import { VERSION, versionLabel } from '$lib/version';
  import Icon from '$lib/components/Icon.svelte';

  let { class: cls = '' }: { class?: string } = $props();

  // Re-tick the relative label so "synced 2m ago" stays current without a reload.
  let now = $state(Date.now());
  $effect(() => {
    const id = setInterval(() => (now = Date.now()), 30_000);
    return () => clearInterval(id);
  });

  const loading = $derived(meta.status === 'loading');

  // #62: the shell knows its own build at compile time; the server's comes from /healthz,
  // which is public (AUTH_PUBLIC) and already the liveness probe. Fetched once on mount —
  // a stale cached PWA against a fresh pod then reads as two numbers on screen instead of
  // looking identical. Any failure (offline, older server) leaves it '' and shows one.
  let server = $state('');
  $effect(() => {
    (async () => {
      try {
        server = ((await (await fetch(base + '/healthz')).json()).version as string) ?? '';
      } catch {
        /* keep '' */
      }
    })();
  });

  async function refresh() {
    await Promise.all([loadAppData(), paid.load()]);
    if (meta.status === 'ready') toast('Refreshed');
  }
</script>

<div class="flex items-center gap-2 text-[12px] {cls}" style="color:var(--muted)">
  <span class="tnum">
    {#if !net.online}<span style="color:#f87171">Offline · </span>{/if}synced {ago(meta.lastSynced, now)}
  </span>
  <button
    type="button"
    onclick={refresh}
    disabled={loading}
    aria-label="Refresh data"
    class="syncbtn"
    class:spin={loading}
    style="color:var(--accent)"
  >
    <Icon name="sync" size={16} />
  </button>
  <span class="tnum" title="App version (shell · server). They differ when a cached PWA is behind the server — reload to pick up the new shell.">
    {versionLabel(VERSION, server)}
  </span>
</div>

<style>
  .syncbtn {
    display: inline-flex;
    padding: 0.25rem;
  }
  .syncbtn:focus-visible {
    outline: 2px solid var(--text);
    outline-offset: 2px;
  }
  .spin {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
