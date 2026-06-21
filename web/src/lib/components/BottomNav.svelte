<script lang="ts">
  import { page } from '$app/state';
  import Icon from './Icon.svelte';
  const tabs = [
    { href: '/', label: 'Home', icon: 'wallet-outline' },
    { href: '/trends', label: 'Trends', icon: 'chart-line' },
    { href: '/cuts', label: 'Cuts', icon: 'content-cut' }
  ];
  const path = $derived(page.url.pathname);
</script>
<nav class="fixed bottom-0 inset-x-0 flex border-t" style="border-color:var(--divider);background:var(--bg)">
  {#each tabs as t}
    {@const on = path === t.href}
    <a href={t.href} aria-current={on ? 'page' : undefined}
       class="flex-1 flex flex-col items-center gap-1 py-3 text-[11px] font-bold uppercase tracking-wide"
       style="color:{on ? 'var(--accent)' : 'var(--muted)'}">
      <Icon name={t.icon} size={22} />
      {t.label}
    </a>
  {/each}
</nav>
