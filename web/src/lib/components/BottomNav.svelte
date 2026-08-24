<script lang="ts">
  import { page } from '$app/state';
  import { base } from '$app/paths';
  import { onMount } from 'svelte';
  import Icon from './Icon.svelte';
  import { search, MAGNIFY } from '$lib/search.svelte';
  import { ensureSettings, markSetupSeen, nagSetup } from '$lib/setupnag.svelte';
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
  const SETTINGS = base + '/settings';

  // #96: shared with TopBar, which is mounted at this width too (lg:hidden is display:none,
  // not an unmount) — so this is one GET of /api/settings between the two navs, not two.
  onMount(ensureSettings);
  $effect(() => {
    if (path === SETTINGS) markSetupSeen();
  });
  // CALL IT — see the note on nagSetup. Unread it is a truthy function object, and the cog
  // would pulse at a fully configured user forever with nothing to catch it.
  const nag = $derived(nagSetup());
</script>
<nav class="fixed bottom-0 inset-x-0 flex border-t" style="border-color:var(--divider);background:var(--bg)">
  {#each tabs as t}
    {@const on = path === t.href}
    <!-- #96: the ring rides the tab anchor, positioned over where the icon sits, rather
         than on the icon itself — on a first run app.json is absent, app.icons is empty and
         Icon draws its square-outline fallback (#64), so the glyph is not a stable anchor. -->
    {@const ring = t.href === SETTINGS && nag}
    <a href={t.href} aria-current={on ? 'page' : undefined}
       title={ring ? 'Finish setup' : undefined}
       class="flex-1 flex flex-col items-center gap-1 py-3 text-[12px] font-bold uppercase tracking-wide {ring ? 'nag' : ''}"
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

<style>
  /* #96: a 30px circle over the icon, not around the whole tab — a tab is 65px wide at
     390px and a ring on its box would scale into its neighbours. 30px at 1.35 is 41px. */
  .nag {
    position: relative;
  }
  .nag::after {
    content: '';
    position: absolute;
    top: 8px;
    left: 50%;
    width: 30px;
    height: 30px;
    margin-left: -15px;
    border-radius: 9999px;
    border: 2px solid var(--accent);
    pointer-events: none;
    animation: nagpulse 2.4s ease-out infinite;
  }
  @keyframes nagpulse {
    0% {
      transform: scale(0.85);
      opacity: 0.9;
    }
    70%,
    100% {
      transform: scale(1.35);
      opacity: 0;
    }
  }
  /* Same floor as everywhere else: the animation goes, the state stays — a static dot on
     the corner of the cog instead of a ring that expands. */
  @media (prefers-reduced-motion: reduce) {
    .nag::after {
      top: 9px;
      margin-left: 5px;
      width: 8px;
      height: 8px;
      border: 0;
      background: var(--accent);
      animation: none;
    }
  }
</style>
