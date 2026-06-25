<script lang="ts">
  import { page } from '$app/state';
  import Icon from './Icon.svelte';
  import { search, MAGNIFY } from '$lib/search.svelte';
  const tabs = [
    { href: '/', label: 'Home', icon: 'wallet-outline' },
    { href: '/trends', label: 'Trends', icon: 'chart-line' },
    { href: '/cuts', label: 'Cuts', icon: 'content-cut' },
    { href: '/fees', label: 'Fees', icon: 'receipt-text-outline' }
  ];
  const path = $derived(page.url.pathname);
</script>
<nav class="fixed bottom-0 inset-x-0 flex border-t" style="border-color:var(--divider);background:var(--bg)">
  {#each tabs as t}
    {@const on = path === t.href}
    <a href={t.href} aria-current={on ? 'page' : undefined}
       class="flex-1 flex flex-col items-center gap-1 py-3 text-[12px] font-bold uppercase tracking-wide"
       style="color:{on ? 'var(--accent)' : 'var(--muted)'}">
      <Icon name={t.icon} size={22} />
      {t.label}
    </a>
  {/each}
  <button type="button" onclick={() => (search.open = true)} aria-label="Search transactions"
    class="flex-1 flex flex-col items-center gap-1 py-3 text-[12px] font-bold uppercase tracking-wide border-0 bg-transparent"
    style="color:var(--muted)">
    <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true"><path d={MAGNIFY} /></svg>
    Find
  </button>
</nav>
