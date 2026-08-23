<script lang="ts">
  import { page } from '$app/state';
  import { base } from '$app/paths';
  import Icon from './Icon.svelte';
  import { search, MAGNIFY } from '$lib/search.svelte';
  const tabs = [
    { href: base || '/', label: 'Home', icon: 'wallet-outline' },
    { href: base + '/trends', label: 'Trends', icon: 'chart-line' },
    { href: base + '/cuts', label: 'Cuts', icon: 'content-cut' },
    { href: base + '/fees', label: 'Fees', icon: 'receipt-text-outline' },
    // #66: settings is where credentials/mail/reminders live, so it belongs on the one
    // navigation surface a phone user learns — not a corner of a header that scrolls away.
    // 6 slots is 65px each at 390px; audit-responsive.mjs says the full label still fits,
    // so it was not shortened. Adding a 7th would be the point to re-measure.
    { href: base + '/settings', label: 'Settings', icon: 'cog-outline' }
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
