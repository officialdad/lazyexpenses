<script lang="ts">
  import { meta, loadAppData } from '$lib/data';
  import { paid } from '$lib/paid.svelte';
  import { net } from '$lib/net.svelte';
  import { ago } from '$lib/fmt';
  import { toast } from '$lib/toast.svelte';
  import Icon from '$lib/components/Icon.svelte';

  let { class: cls = '' }: { class?: string } = $props();

  // Re-tick the relative label so "synced 2m ago" stays current without a reload.
  let now = $state(Date.now());
  $effect(() => {
    const id = setInterval(() => (now = Date.now()), 30_000);
    return () => clearInterval(id);
  });

  const loading = $derived(meta.status === 'loading');

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
